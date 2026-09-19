"""
DB 계층 — SQLite(기본)와 PostgreSQL(운영)을 같은 코드로 다룬다.

    DATABASE_URL 이 없으면            → SQLite  (TJ_DB 경로, 개인용·단일 서버)
    DATABASE_URL=postgresql://... 이면 → PostgreSQL (Supabase / Neon / Render / 자체 호스팅)

애플리케이션 코드는 항상 SQLite 문법(`?` 자리표시자)으로 쿼리를 쓰고,
PostgreSQL일 때 이 모듈이 `%s` 로 바꿔 보낸다. 두 엔진 모두
`INSERT ... ON CONFLICT(id) DO UPDATE SET x=excluded.x` 문법을 지원한다.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
Row = Any  # sqlite3.Row 또는 dict — 둘 다 r["col"] 로 읽는다

_pool = None
if IS_PG:  # pragma: no cover - 운영 경로
    import psycopg
    from psycopg.rows import dict_row

    try:
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=int(os.environ.get("TJ_PG_MIN", "1")),
            max_size=int(os.environ.get("TJ_PG_MAX", "10")),
            kwargs={"row_factory": dict_row},
            open=True,
        )
    except Exception:  # psycopg_pool 이 없으면 요청마다 연결
        _pool = None


def _q(sql: str) -> str:
    """`?` 자리표시자를 psycopg 의 `%s` 로 바꾼다 (쿼리는 모두 코드 내 상수)."""
    return sql.replace("%", "%%").replace("?", "%s") if IS_PG else sql


class _PGCursor:
    def __init__(self, cur: Any) -> None:
        self._cur = cur

    def fetchone(self) -> Optional[dict[str, Any]]:
        return self._cur.fetchone()

    def fetchall(self) -> list[dict[str, Any]]:
        return self._cur.fetchall()


class Conn:
    """execute / executescript / insert_id / columns 만 제공하는 얇은 래퍼."""

    def __init__(self, raw: Any) -> None:
        self.raw = raw

    # -- 공통 API ---------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        if IS_PG:
            cur = self.raw.cursor()
            cur.execute(_q(sql), tuple(params))
            return _PGCursor(cur)
        return self.raw.execute(sql, tuple(params))

    def executescript(self, sql: str) -> None:
        if IS_PG:
            with self.raw.cursor() as cur:
                for stmt in [s.strip() for s in sql.split(";")]:
                    if stmt:
                        cur.execute(stmt)
            return
        self.raw.executescript(sql)

    def insert_id(self, sql: str, params: Sequence[Any]) -> int:
        """INSERT 후 새 정수 PK 를 돌려준다 (sqlite: lastrowid, pg: RETURNING id)."""
        if IS_PG:
            cur = self.raw.cursor()
            cur.execute(_q(sql) + " RETURNING id", tuple(params))
            return int(cur.fetchone()["id"])
        return int(self.raw.execute(sql, tuple(params)).lastrowid)

    def columns(self, table: str) -> set[str]:
        if IS_PG:
            rows = self.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=?", (table,)
            ).fetchall()
            return {r["column_name"] for r in rows}
        return {r["name"] for r in self.raw.execute(f"PRAGMA table_info({table})").fetchall()}


@contextmanager
def connect(sqlite_path: Path) -> Iterator[Conn]:
    if IS_PG:  # pragma: no cover - 운영 경로
        if _pool is not None:
            with _pool.connection() as raw:  # 풀이 커밋/롤백을 처리
                yield Conn(raw)
            return
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            yield Conn(raw)
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
        return

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(sqlite_path, timeout=15)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA foreign_keys=ON")
    try:
        yield Conn(raw)
        raw.commit()
    finally:
        raw.close()


# --------------------------------------------------------------------------- 스키마
SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT UNIQUE NOT NULL,
    pw_hash    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    id         TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date       TEXT NOT NULL,
    time       TEXT,
    symbol     TEXT NOT NULL,
    side       TEXT,
    entry      REAL, exit REAL, qty REAL, fee REAL,
    pnl        REAL, pnl_pct REAL,
    tags       TEXT, comment TEXT, lesson TEXT, rating INTEGER,
    is_lesson  INTEGER NOT NULL DEFAULT 0,
    is_market  INTEGER NOT NULL DEFAULT 0,
    align_from TEXT DEFAULT '', align_to TEXT DEFAULT '',
    images     TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_user_date ON entries(user_id, date);
CREATE TABLE IF NOT EXISTS images (
    id         TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mime       TEXT NOT NULL,
    data       BLOB NOT NULL,
    thumb      BLOB,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_images_user ON images(user_id);
"""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS users (
    id         BIGSERIAL PRIMARY KEY,
    username   TEXT UNIQUE NOT NULL,
    pw_hash    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    id         TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date       TEXT NOT NULL,
    time       TEXT,
    symbol     TEXT NOT NULL,
    side       TEXT,
    entry      DOUBLE PRECISION, exit DOUBLE PRECISION,
    qty        DOUBLE PRECISION, fee DOUBLE PRECISION,
    pnl        DOUBLE PRECISION, pnl_pct DOUBLE PRECISION,
    tags       TEXT, comment TEXT, lesson TEXT, rating INTEGER,
    is_lesson  INTEGER NOT NULL DEFAULT 0,
    is_market  INTEGER NOT NULL DEFAULT 0,
    align_from TEXT DEFAULT '', align_to TEXT DEFAULT '',
    images     TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_user_date ON entries(user_id, date);
CREATE TABLE IF NOT EXISTS images (
    id         TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mime       TEXT NOT NULL,
    data       BYTEA NOT NULL,
    thumb      BYTEA,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_images_user ON images(user_id);
"""


def schema() -> str:
    return SCHEMA_PG if IS_PG else SCHEMA_SQLITE


def backend() -> str:
    return "postgres" if IS_PG else "sqlite"
