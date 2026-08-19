#!/usr/bin/env python3
"""
독립 저장소(ch-trading) 트리를 이 저장소에서 생성한다.

매매일지는 POSCO PPI 앱과 무관하므로, 상업 서비스용으로는 저장소 루트가 곧 사이트인
독립 저장소로 배포한다 (Vercel에서 Root Directory 설정이 필요 없음).

사용법:
    python tools/make-standalone.py [출력경로]        # 기본: ../ch-trading
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT.parent / "ch-trading"

COPY = [
    ("trading-journal/index.html", "index.html"),
    ("trading-journal/config.js", "config.js"),
    ("trading-journal/README.md", "README.md"),
    ("server/main.py", "server/main.py"),
    ("server/requirements.txt", "server/requirements.txt"),
    ("server/Dockerfile", "server/Dockerfile"),
    ("server/.env.example", "server/.env.example"),
    ("server/README.md", "server/README.md"),
    ("supabase/schema.sql", "supabase/schema.sql"),
    ("supabase/README.md", "supabase/README.md"),
    ("docs/DEPLOY-VERCEL.md", "docs/DEPLOY-VERCEL.md"),
    ("docs/legal/README.md", "docs/legal/README.md"),
    ("docs/legal/이용약관.md", "docs/legal/이용약관.md"),
    ("docs/legal/개인정보처리방침.md", "docs/legal/개인정보처리방침.md"),
    ("docs/legal/환불정책.md", "docs/legal/환불정책.md"),
    (".github/workflows/supabase-keepalive.yml", ".github/workflows/supabase-keepalive.yml"),
]

# 독립 저장소에서는 화면 파일이 루트에 있으므로 경로 표기를 바꾼다
REWRITES = {
    "server/main.py": [
        ('WEB_DIR = ROOT / "trading-journal"',
         "WEB_DIR = ROOT                      # 화면 파일(index.html, config.js)은 저장소 루트에 있다"),
        ("- 프런트엔드(trading-journal/index.html)를 그대로 서빙하며, 프런트는 서버가 있으면",
         "- 화면(index.html)을 그대로 서빙하며, 프런트는 서버가 있으면"),
    ],
    "server/Dockerfile": [
        ("COPY server ./server\nCOPY trading-journal ./trading-journal",
         "COPY server ./server\nCOPY index.html config.js ./"),
    ],
    "server/README.md": [
        ("- 프런트엔드(`trading-journal/`)도 이 서버가 함께 서빙합니다",
         "- 화면(`index.html`, `config.js`)도 이 서버가 함께 서빙합니다"),
        ("`trading-journal/index.html` 은 시작할 때", "`index.html` 은 시작할 때"),
    ],
    "supabase/README.md": [
        ("[`trading-journal/config.js`](../trading-journal/config.js)", "[`config.js`](../config.js)"),
        ("이 저장소의 [`supabase/schema.sql`](schema.sql)", "이 저장소의 [`schema.sql`](schema.sql)"),
    ],
    "README.md": [
        ("`trading-journal/index.html` 파일을 더블클릭", "`index.html` 파일을 더블클릭"),
        ("[`supabase/README.md`](../supabase/README.md)", "[`supabase/README.md`](supabase/README.md)"),
        ("[`server/README.md`](../server/README.md)", "[`server/README.md`](server/README.md)"),
        ("[`docs/DEPLOY-VERCEL.md`](../docs/DEPLOY-VERCEL.md)", "[`docs/DEPLOY-VERCEL.md`](docs/DEPLOY-VERCEL.md)"),
    ],
}

# 화면 파일만 서빙하도록 정적 마운트를 대체 (소스 노출 방지)
STATIC_OLD = '''# --------------------------------------------------------------------------- 정적 파일
@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")'''

STATIC_NEW = '''# --------------------------------------------------------------------------- 화면 파일
# 저장소 루트를 그대로 공개하면 server/·supabase/ 소스까지 노출되므로,
# 화면에 필요한 파일만 골라서 서빙한다.
@app.get("/")
@app.get("/index.html")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html",
                        headers={"Cache-Control": "no-cache"})


@app.get("/config.js")
def config_js() -> Response:
    path = WEB_DIR / "config.js"
    if not path.exists():
        return Response(content="window.TJ_CONFIG = {};", media_type="application/javascript")
    return FileResponse(path, media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})'''

VERCEL_JSON = """{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "cleanUrls": true,
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=0, must-revalidate" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" }
      ]
    }
  ]
}
"""

GITIGNORE = """# 서버 데이터 (SQLite)
server/data/
*.db
*.db-wal
*.db-shm

# Python
__pycache__/
*.pyc
.venv/
venv/

# OS
.DS_Store
"""


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for src, dst in COPY:
        target = OUT / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / src, target)

    for rel, pairs in REWRITES.items():
        path = OUT / rel
        text = path.read_text(encoding="utf-8")
        for old, new in pairs:
            if old not in text:
                print(f"  ! 치환 대상 없음: {rel} <- {old[:40]}...")
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

    main_py = OUT / "server/main.py"
    text = main_py.read_text(encoding="utf-8")
    if STATIC_OLD not in text:
        raise SystemExit("server/main.py 의 정적 서빙 블록을 찾지 못했습니다 — 스크립트를 갱신하세요.")
    text = text.replace(STATIC_OLD, STATIC_NEW).replace(
        "from fastapi.staticfiles import StaticFiles\n", "")
    main_py.write_text(text, encoding="utf-8")

    (OUT / "vercel.json").write_text(VERCEL_JSON, encoding="utf-8")
    (OUT / ".gitignore").write_text(GITIGNORE, encoding="utf-8")

    print(f"✅ 생성 완료: {OUT}")
    print("   다음: cd", OUT, "&& git init -b main && git add -A && git commit && git push")


if __name__ == "__main__":
    main()
