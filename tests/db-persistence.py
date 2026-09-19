#!/usr/bin/env python3
"""
DB 검증 — 서버를 껐다 켜도 일지·차트 이미지가 그대로 남는지 확인한다.

    python3 tests/db-persistence.py                       # SQLite
    TJ_TEST_DATABASE_URL=postgresql://... python3 tests/db-persistence.py   # PostgreSQL

브라우저 테스트와 달리 API 만 두드리므로 몇 초면 끝난다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("TJ_TEST_PORT", "8061"))
BASE = f"http://127.0.0.1:{PORT}"
DB_URL = os.environ.get("TJ_TEST_DATABASE_URL", "")
SECRET = "db-persistence-test-secret"
PNG = ROOT / "tests" / ".tmp" / "chart.png"

jar = CookieJar()
http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with http.open(req, timeout=20) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def upload(png: bytes) -> str:
    boundary = "----tjtest" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="chart.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + png + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "/api/images", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with http.open(req, timeout=30) as r:
        return json.loads(r.read())["id"]


def fetch(path: str) -> bytes:
    with http.open(urllib.request.Request(BASE + path), timeout=20) as r:
        return r.read()


def start(db_file: Path) -> subprocess.Popen:
    env = {**os.environ, "TJ_SECRET": SECRET, "TJ_ALLOW_REGISTER": "1",
           "TJ_DB": str(db_file), "DATABASE_URL": DB_URL}
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            return p if call("GET", "/api/health")["ok"] else p
        except Exception:
            time.sleep(0.5)
    p.terminate()
    raise SystemExit("✗ 서버가 뜨지 않았습니다")


def stop(p: subprocess.Popen) -> None:
    p.terminate()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"✗ {msg}")


def main() -> None:
    if not PNG.exists():
        subprocess.run([sys.executable, "tests/fixtures/make-charts.py", str(PNG.parent)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    png = PNG.read_bytes()
    user = "dbtest" + uuid.uuid4().hex[:8]
    entry_id = "e-" + uuid.uuid4().hex[:10]

    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "persist.db"

        srv = start(db_file)
        health = call("GET", "/api/health")
        backend = health.get("db")
        check(backend in ("sqlite", "postgres"), f"알 수 없는 DB: {health}")
        check(bool(DB_URL) == (backend == "postgres"), f"DB 선택이 어긋남: {backend}")
        print(f"  DB: {backend}")

        call("POST", "/api/auth/register", {"username": user, "password": "journal1234"})
        img_id = upload(png)
        saved = call("PUT", f"/api/entries/{entry_id}", {
            "id": entry_id, "date": "2026-09-19", "symbol": "삼성전자", "side": "long",
            "entry": 71500, "exit": 73200, "qty": 100, "pnl": 170000, "pnlPct": 2.38,
            "tags": ["돌파", "장초반"], "comment": "거래량 실린 돌파",
            "lesson": "거래량 없는 돌파는 따라가지 않는다", "isLesson": True,
            "alignFrom": "역배열", "alignTo": "정배열", "rating": 4, "images": [img_id],
        })
        check(saved["images"] == [img_id], "저장 응답에 이미지가 없습니다")
        stop(srv)

        # --- 서버 재시작 후에도 같은 데이터가 보여야 한다 -----------------
        srv = start(db_file)
        try:
            call("GET", "/api/me")  # 쿠키는 TJ_SECRET 이 같으므로 재시작 후에도 유효
            entries = call("GET", "/api/entries")
            check(len(entries) == 1, f"일지 개수가 1이 아닙니다: {len(entries)}")
            e = entries[0]
            check(e["id"] == entry_id and e["symbol"] == "삼성전자", "일지 내용이 달라졌습니다")
            check(e["lesson"] == "거래량 없는 돌파는 따라가지 않는다", "시사점이 보존되지 않았습니다")
            check(e["isLesson"] is True, "시사점 플래그가 보존되지 않았습니다")
            check(e["alignFrom"] == "역배열" and e["alignTo"] == "정배열", "배열 기록이 보존되지 않았습니다")
            check(e["tags"] == ["돌파", "장초반"], "태그가 보존되지 않았습니다")
            check(abs(e["pnl"] - 170000) < 1e-6, "손익 숫자가 보존되지 않았습니다")

            blob = fetch(f"/api/images/{img_id}")
            check(blob == png, f"이미지 바이트가 달라졌습니다 ({len(blob)} vs {len(png)})")

            backup = call("GET", "/api/export")
            check(len(backup["entries"]) == 1 and len(backup["images"]) == 1, "백업 JSON이 비었습니다")

            # 남의 데이터가 보이면 안 된다
            jar.clear()
            other = "dbtest" + uuid.uuid4().hex[:8]
            call("POST", "/api/auth/register", {"username": other, "password": "journal1234"})
            check(call("GET", "/api/entries") == [], "다른 계정에 남의 일지가 보입니다")
            try:
                fetch(f"/api/images/{img_id}")
                raise SystemExit("✗ 다른 계정이 남의 이미지를 받았습니다")
            except urllib.error.HTTPError as err:
                check(err.code == 404, f"남의 이미지 응답 코드가 404가 아닙니다: {err.code}")
        finally:
            stop(srv)

    print(f"✓ db-persistence ({backend}) — 재시작 후 일지·이미지·계정 격리 모두 유지")


if __name__ == "__main__":
    main()
