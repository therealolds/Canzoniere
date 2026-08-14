#!/usr/bin/env python3
"""Generate placeholder PWA icons (green tile + white note dot). Stdlib only.

Run once (or after editing):   py scripts/make_icons.py
Replace icons/ with real artwork whenever you like.
"""
import struct
import zlib
from pathlib import Path

ICONS = Path(__file__).resolve().parent.parent / "icons"
GREEN = (46, 125, 50)
WHITE = (245, 245, 240)


def make_png(size):
    cx = cy = size / 2
    r = size * 0.26
    stem_x0, stem_x1 = cx + r * 0.75, cx + r * 1.05
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # PNG filter type 0 for this scanline
        for x in range(size):
            # note head (filled circle) + a simple stem
            in_head = (x - cx) ** 2 + (y - cy + r * 0.35) ** 2 <= r * r
            in_stem = stem_x0 <= x <= stem_x1 and (cy - r * 1.4) <= y <= (cy + r * 0.1)
            rows += bytes(WHITE if (in_head or in_stem) else GREEN)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + chunk(b"IEND", b""))


def main():
    ICONS.mkdir(exist_ok=True)
    for size in (192, 512):
        (ICONS / f"icon-{size}.png").write_bytes(make_png(size))
        print(f"wrote icons/icon-{size}.png")


if __name__ == "__main__":
    main()
