#!/usr/bin/env python3
"""Generate the PWA icons from icons/icon-source.jpeg.

Center-crops the source to a square, then resizes to the sizes the manifest
references. Requires Pillow (pip install pillow).

Run:   py scripts/make_icons.py
"""
from pathlib import Path

from PIL import Image

ICONS = Path(__file__).resolve().parent.parent / "icons"
SOURCE = ICONS / "icon-source.jpeg"
SIZES = (192, 512)


def main():
    if not SOURCE.exists():
        raise SystemExit(f"Source image not found: {SOURCE}")

    img = Image.open(SOURCE).convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    square = img.crop((left, top, left + side, top + side))

    for size in SIZES:
        out = square.resize((size, size), Image.LANCZOS)
        out.save(ICONS / f"icon-{size}.png", "PNG")
        print(f"wrote icons/icon-{size}.png")

    # Transparent header mark: chroma-key the near-black background away so the
    # amber art blends into the dark top bar (or any background).
    mark = square.resize((128, 128), Image.LANCZOS).convert("RGBA")
    px = mark.load()
    for y in range(128):
        for x in range(128):
            r, g, b, _ = px[x, y]
            luma = 0.299 * r + 0.587 * g + 0.114 * b
            alpha = 0 if luma < 18 else min(255, int((luma - 14) * 4))
            px[x, y] = (r, g, b, alpha)
    mark.save(ICONS / "mark.png", "PNG")
    print("wrote icons/mark.png")


if __name__ == "__main__":
    main()
