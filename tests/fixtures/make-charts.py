#!/usr/bin/env python3
"""테스트용 차트 캡처 PNG 생성 (외부 의존성 없음)."""
import os, struct, sys, zlib

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", ".tmp")
os.makedirs(OUT, exist_ok=True)


def write_png(path: str, w: int, h: int) -> int:
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            row += bytes([(x * 255) // w, (y * 255) // h, 180])
        rows.append(bytes(row))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


for name, (w, h) in {"chart.png": (120, 120), "chart-big.png": (1600, 900)}.items():
    size = write_png(os.path.join(OUT, name), w, h)
    print(f"{name}: {w}x{h}, {size // 1024}KB")
