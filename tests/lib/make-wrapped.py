#!/usr/bin/env python3
"""아티팩트(임베드) 검증용 파일 생성 — index.html 을 <head>/<body> 없이 감싼 형태."""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tests", ".tmp")
os.makedirs(TMP, exist_ok=True)

src = open(os.path.join(ROOT, "trading-journal", "index.html"), encoding="utf-8").read()
style = src[src.index("<style>"):src.index("</head>")].strip()
body = src[src.index("<body>") + len("<body>"):src.rindex("</body>")].strip()
page = "<title>매매일지</title>\n" + style + "\n" + body + "\n"

for tag in ["<!DOCTYPE", "<html", "<head>", "</head>", "<body>", "</body>", "</html>", "config.js"]:
    assert tag not in page, f"아티팩트 본문에 {tag} 가 남아 있습니다"

open(os.path.join(TMP, "artifact.html"), "w", encoding="utf-8").write(page)
open(os.path.join(TMP, "wrapped.html"), "w", encoding="utf-8").write(
    '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1"></head><body>' + page + "</body></html>")
open(os.path.join(TMP, "embed.html"), "w", encoding="utf-8").write(
    '<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;height:100%}'
    'iframe{border:0;width:100%;height:100%}</style></head><body>'
    '<iframe src="wrapped.html" sandbox="allow-scripts allow-same-origin allow-modals"></iframe>'
    "</body></html>")
print(f"artifact.html / wrapped.html / embed.html → {TMP}  ({len(page)//1024}KB)")
