"""
매매일지 서버 (FastAPI + SQLite)

- 계정별로 일지/차트 이미지를 서버 DB에 저장합니다. 어느 기기에서 접속해도 같은 기록이 보입니다.
- 프런트엔드(trading-journal/index.html)를 그대로 서빙하며, 프런트는 서버가 있으면
  서버 모드, 없으면(파일로 직접 열기 등) 브라우저 저장 모드로 자동 전환됩니다.

실행:
    pip install -r server/requirements.txt
    export TJ_SECRET="$(python -c 'import secrets;print(secrets.token_hex(32))')"
    uvicorn server.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- 설정
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "trading-journal"
DB_PATH = Path(os.environ.get("TJ_DB", ROOT / "server" / "data" / "journal.db"))
COOKIE = "tj_session"
SESSION_DAYS = int(os.environ.get("TJ_SESSION_DAYS", "30"))
MAX_IMAGE_BYTES = int(os.environ.get("TJ_MAX_IMAGE_MB", "8")) * 1024 * 1024
ALLOW_REGISTER = os.environ.get("TJ_ALLOW_REGISTER", "auto").lower()  # auto | 1 | 0
PBKDF2_ROUNDS = 200_000

_SECRET_ENV = os.environ.get("TJ_SECRET")
SECRET = (_SECRET_ENV or secrets.token_hex(32)).encode()
SECRET_IS_EPHEMERAL = _SECRET_ENV is None

app = FastAPI(title="매매일지 API", docs_url="/api/docs", openapi_url="/api/openapi.json")


# --------------------------------------------------------------------------- DB
@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with db() as con:
        con.executescript(
            """
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
        )


def migrate_db() -> None:
    """이전 버전 DB에 새 컬럼을 더한다."""
    with db() as con:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(entries)").fetchall()}
        if "lesson" not in cols:
            con.execute("ALTER TABLE entries ADD COLUMN lesson TEXT DEFAULT ''")
        if "is_lesson" not in cols:
            con.execute("ALTER TABLE entries ADD COLUMN is_lesson INTEGER NOT NULL DEFAULT 0")


init_db()
migrate_db()


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


# --------------------------------------------------------------------------- 인증
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, rounds, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def make_token(user_id: int) -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    body = f"{user_id}.{exp}"
    sig = hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def read_token(token: str) -> Optional[int]:
    try:
        uid, exp, sig = token.split(".")
        body = f"{uid}.{exp}"
        good = hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, good) or int(exp) < time.time():
            return None
        return int(uid)
    except Exception:
        return None


def current_user(request: Request) -> sqlite3.Row:
    token = request.cookies.get(COOKIE, "")
    uid = read_token(token) if token else None
    if uid is None:
        raise HTTPException(401, "로그인이 필요합니다")
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다")
    return user


def user_count() -> int:
    with db() as con:
        return con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def registration_open() -> bool:
    if ALLOW_REGISTER in ("1", "true", "yes"):
        return True
    if ALLOW_REGISTER in ("0", "false", "no"):
        return False
    return user_count() == 0  # auto: 첫 사용자(관리자)만 가입 허용


def set_session_cookie(response: Response, request: Request, user_id: int) -> None:
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        COOKIE, make_token(user_id),
        max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=secure, path="/",
    )


# --------------------------------------------------------------------------- 모델
class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=6, max_length=200)


class Entry(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = ""
    symbol: str = Field(min_length=1, max_length=120)
    side: str = "long"
    entry: Optional[float] = None
    exit: Optional[float] = None
    qty: Optional[float] = None
    fee: Optional[float] = None
    pnl: Optional[float] = None
    pnlPct: Optional[float] = None
    tags: list[str] = []
    comment: str = ""
    lesson: str = ""
    isLesson: bool = False
    rating: int = 0
    images: list[str] = []
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


def row_to_entry(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"], "date": r["date"], "time": r["time"] or "", "symbol": r["symbol"],
        "side": r["side"] or "long", "entry": r["entry"], "exit": r["exit"], "qty": r["qty"],
        "fee": r["fee"], "pnl": r["pnl"], "pnlPct": r["pnl_pct"],
        "tags": json.loads(r["tags"] or "[]"), "comment": r["comment"] or "",
        "lesson": r["lesson"] or "", "isLesson": bool(r["is_lesson"]),
        "rating": r["rating"] or 0, "images": json.loads(r["images"] or "[]"),
        "createdAt": r["created_at"], "updatedAt": r["updated_at"],
    }


# --------------------------------------------------------------------------- 인증 API
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "mode": "server", "registrationOpen": registration_open()}


@app.get("/api/me")
def me(user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    return {"username": user["username"], "createdAt": user["created_at"]}


@app.post("/api/auth/register")
def register(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
    if not registration_open():
        raise HTTPException(403, "이 서버는 신규 가입이 닫혀 있습니다")
    username = body.username.strip().lower()
    with db() as con:
        if con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(409, "이미 사용 중인 아이디입니다")
        cur = con.execute(
            "INSERT INTO users (username, pw_hash, created_at) VALUES (?,?,?)",
            (username, hash_password(body.password), now()),
        )
        uid = int(cur.lastrowid)
    set_session_cookie(response, request, uid)
    return {"username": username}


@app.post("/api/auth/login")
def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
    username = body.username.strip().lower()
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if user is None or not verify_password(body.password, user["pw_hash"]):
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다")
    set_session_cookie(response, request, int(user["id"]))
    return {"username": user["username"]}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.post("/api/auth/password")
def change_password(body: Credentials, user: sqlite3.Row = Depends(current_user)) -> dict[str, bool]:
    """현재 로그인한 계정의 비밀번호를 변경합니다. username 자리에 현재 비밀번호를 보냅니다."""
    if not verify_password(body.username, user["pw_hash"]):
        raise HTTPException(401, "현재 비밀번호가 올바르지 않습니다")
    with db() as con:
        con.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_password(body.password), user["id"]))
    return {"ok": True}


# --------------------------------------------------------------------------- 일지 API
@app.get("/api/entries")
def list_entries(user: sqlite3.Row = Depends(current_user)) -> list[dict[str, Any]]:
    with db() as con:
        rows = con.execute(
            "SELECT * FROM entries WHERE user_id=? ORDER BY date, time", (user["id"],)
        ).fetchall()
    return [row_to_entry(r) for r in rows]


def _owned_images(con: sqlite3.Connection, user_id: int, ids: list[str]) -> list[str]:
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = con.execute(
        f"SELECT id FROM images WHERE user_id=? AND id IN ({marks})", (user_id, *ids)
    ).fetchall()
    owned = {r["id"] for r in rows}
    return [i for i in ids if i in owned]


@app.put("/api/entries/{entry_id}")
def upsert_entry(entry_id: str, body: Entry, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    if entry_id != body.id:
        raise HTTPException(400, "id가 일치하지 않습니다")
    with db() as con:
        old = con.execute(
            "SELECT * FROM entries WHERE id=? AND user_id=?", (entry_id, user["id"])
        ).fetchone()
        images = _owned_images(con, int(user["id"]), body.images)
        # 이 일지에서 떨어져 나간 이미지는 함께 정리
        if old:
            dropped = [i for i in json.loads(old["images"] or "[]") if i not in images]
            for img_id in dropped:
                con.execute("DELETE FROM images WHERE id=? AND user_id=?", (img_id, user["id"]))
        con.execute(
            """INSERT INTO entries
               (id,user_id,date,time,symbol,side,entry,exit,qty,fee,pnl,pnl_pct,tags,comment,lesson,is_lesson,rating,images,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 date=excluded.date, time=excluded.time, symbol=excluded.symbol, side=excluded.side,
                 entry=excluded.entry, exit=excluded.exit, qty=excluded.qty, fee=excluded.fee,
                 pnl=excluded.pnl, pnl_pct=excluded.pnl_pct, tags=excluded.tags, comment=excluded.comment,
                 lesson=excluded.lesson, is_lesson=excluded.is_lesson,
                 rating=excluded.rating, images=excluded.images, updated_at=excluded.updated_at""",
            (
                body.id, user["id"], body.date, body.time, body.symbol, body.side,
                body.entry, body.exit, body.qty, body.fee, body.pnl, body.pnlPct,
                json.dumps(body.tags, ensure_ascii=False), body.comment, body.lesson,
                1 if body.isLesson else 0, body.rating,
                json.dumps(images), (old["created_at"] if old else (body.createdAt or now())), now(),
            ),
        )
        row = con.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
    return row_to_entry(row)


@app.delete("/api/entries/{entry_id}")
def delete_entry(entry_id: str, user: sqlite3.Row = Depends(current_user)) -> dict[str, bool]:
    with db() as con:
        row = con.execute(
            "SELECT * FROM entries WHERE id=? AND user_id=?", (entry_id, user["id"])
        ).fetchone()
        if row is None:
            raise HTTPException(404, "일지를 찾을 수 없습니다")
        for img_id in json.loads(row["images"] or "[]"):
            con.execute("DELETE FROM images WHERE id=? AND user_id=?", (img_id, user["id"]))
        con.execute("DELETE FROM entries WHERE id=? AND user_id=?", (entry_id, user["id"]))
    return {"ok": True}


@app.delete("/api/entries")
def delete_all(user: sqlite3.Row = Depends(current_user)) -> dict[str, bool]:
    with db() as con:
        con.execute("DELETE FROM entries WHERE user_id=?", (user["id"],))
        con.execute("DELETE FROM images WHERE user_id=?", (user["id"],))
    return {"ok": True}


# --------------------------------------------------------------------------- 이미지 API
@app.post("/api/images")
async def upload_image(
    file: UploadFile = File(...),
    thumb: UploadFile | None = File(None),
    user: sqlite3.Row = Depends(current_user),
) -> dict[str, str]:
    data = await file.read()
    if not data:
        raise HTTPException(400, "빈 파일입니다")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"이미지가 너무 큽니다 (최대 {MAX_IMAGE_BYTES // (1024*1024)}MB)")
    mime = file.content_type or "image/jpeg"
    if not mime.startswith("image/"):
        raise HTTPException(415, "이미지 파일만 올릴 수 있습니다")
    thumb_bytes = await thumb.read() if thumb is not None else None
    img_id = secrets.token_hex(12)
    with db() as con:
        con.execute(
            "INSERT INTO images (id,user_id,mime,data,thumb,created_at) VALUES (?,?,?,?,?,?)",
            (img_id, user["id"], mime, data, thumb_bytes, now()),
        )
    return {"id": img_id}


def _image_response(row: sqlite3.Row, key: str) -> Response:
    blob = row[key] if row[key] is not None else row["data"]
    mime = "image/jpeg" if key == "thumb" and row["thumb"] is not None else row["mime"]
    return Response(
        content=bytes(blob), media_type=mime,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@app.get("/api/images/{image_id}")
def get_image(image_id: str, user: sqlite3.Row = Depends(current_user)) -> Response:
    with db() as con:
        row = con.execute(
            "SELECT * FROM images WHERE id=? AND user_id=?", (image_id, user["id"])
        ).fetchone()
    if row is None:
        raise HTTPException(404, "이미지를 찾을 수 없습니다")
    return _image_response(row, "data")


@app.get("/api/images/{image_id}/thumb")
def get_thumb(image_id: str, user: sqlite3.Row = Depends(current_user)) -> Response:
    with db() as con:
        row = con.execute(
            "SELECT * FROM images WHERE id=? AND user_id=?", (image_id, user["id"])
        ).fetchone()
    if row is None:
        raise HTTPException(404, "이미지를 찾을 수 없습니다")
    return _image_response(row, "thumb")


# --------------------------------------------------------------------------- 백업 API
@app.get("/api/export")
def export_all(user: sqlite3.Row = Depends(current_user)) -> JSONResponse:
    with db() as con:
        entries = [row_to_entry(r) for r in con.execute(
            "SELECT * FROM entries WHERE user_id=? ORDER BY date, time", (user["id"],)).fetchall()]
        images = []
        for r in con.execute("SELECT * FROM images WHERE user_id=?", (user["id"],)).fetchall():
            images.append({
                "id": r["id"],
                "data": f"data:{r['mime']};base64," + base64.b64encode(bytes(r["data"])).decode(),
                "thumb": ("data:image/jpeg;base64," + base64.b64encode(bytes(r["thumb"])).decode())
                         if r["thumb"] is not None else None,
            })
    return JSONResponse({
        "app": "trading-journal", "version": 1, "exportedAt": now(),
        "entries": entries, "images": images,
    })


class ImportPayload(BaseModel):
    entries: list[Entry] = []
    images: list[dict[str, Any]] = []


@app.post("/api/import")
def import_all(payload: ImportPayload, user: sqlite3.Row = Depends(current_user)) -> dict[str, int]:
    imported_images = 0
    with db() as con:
        for im in payload.images:
            data_url = im.get("data") or ""
            if "," not in data_url:
                continue
            head, b64 = data_url.split(",", 1)
            mime = head[5:].split(";")[0] or "image/jpeg"
            try:
                blob = base64.b64decode(b64)
            except Exception:
                continue
            if not blob or len(blob) > MAX_IMAGE_BYTES:
                continue
            thumb_url = im.get("thumb") or ""
            thumb_blob = None
            if "," in thumb_url:
                try:
                    thumb_blob = base64.b64decode(thumb_url.split(",", 1)[1])
                except Exception:
                    thumb_blob = None
            con.execute(
                "INSERT INTO images (id,user_id,mime,data,thumb,created_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data, thumb=excluded.thumb",
                (str(im.get("id") or secrets.token_hex(12)), user["id"], mime, blob, thumb_blob, now()),
            )
            imported_images += 1
        for e in payload.entries:
            images = _owned_images(con, int(user["id"]), e.images)
            con.execute(
                """INSERT INTO entries
                   (id,user_id,date,time,symbol,side,entry,exit,qty,fee,pnl,pnl_pct,tags,comment,lesson,is_lesson,rating,images,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     date=excluded.date, time=excluded.time, symbol=excluded.symbol, side=excluded.side,
                     entry=excluded.entry, exit=excluded.exit, qty=excluded.qty, fee=excluded.fee,
                     pnl=excluded.pnl, pnl_pct=excluded.pnl_pct, tags=excluded.tags, comment=excluded.comment,
                     lesson=excluded.lesson, is_lesson=excluded.is_lesson,
                     rating=excluded.rating, images=excluded.images, updated_at=excluded.updated_at""",
                (
                    e.id, user["id"], e.date, e.time, e.symbol, e.side, e.entry, e.exit, e.qty, e.fee,
                    e.pnl, e.pnlPct, json.dumps(e.tags, ensure_ascii=False), e.comment, e.lesson,
                    1 if e.isLesson else 0, e.rating,
                    json.dumps(images), e.createdAt or now(), now(),
                ),
            )
    return {"entries": len(payload.entries), "images": imported_images}


# --------------------------------------------------------------------------- 정적 파일
@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


@app.on_event("startup")
def _warn_secret() -> None:
    if SECRET_IS_EPHEMERAL:
        print(
            "[매매일지] ⚠️  TJ_SECRET 환경변수가 없어 임시 키를 사용합니다. "
            "서버를 재시작하면 모든 로그인이 풀립니다. 운영 시 반드시 설정하세요:\n"
            "    export TJ_SECRET=\"$(python -c 'import secrets;print(secrets.token_hex(32))')\""
        )
