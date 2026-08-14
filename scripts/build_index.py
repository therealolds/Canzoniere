#!/usr/bin/env python3
"""Scan songs/*.cho and emit songs.json (the site's search/index data).

Run from the project root:   python scripts/build_index.py
No dependencies beyond the Python standard library.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SONGS_DIR = ROOT / "songs"
OUT = ROOT / "songs.json"

DIRECTIVE_RE = re.compile(r"^\{\s*([^:}]+?)\s*(?::\s*(.*?)\s*)?\}\s*$")

# Map ChordPro directive names to the metadata field they set.
META_KEYS = {
    "title": "title", "t": "title",
    "subtitle": "subtitle", "st": "subtitle",
    "key": "key",
}
CATEGORY_KEYS = {"categories", "category", "tags"}


def parse_meta(text):
    meta = {"title": "", "subtitle": "", "key": "", "categories": []}
    for line in text.splitlines():
        m = DIRECTIVE_RE.match(line)
        if not m:
            continue
        name = m.group(1).lower()
        value = (m.group(2) or "").strip()
        if name in META_KEYS:
            meta[META_KEYS[name]] = value
        elif name in CATEGORY_KEYS:
            meta["categories"] = [c.strip() for c in value.split(",") if c.strip()]
    return meta


def main():
    if not SONGS_DIR.is_dir():
        sys.exit(f"No songs directory found at {SONGS_DIR}")

    songs = []
    warnings = []
    for path in sorted(SONGS_DIR.glob("*.cho")):
        text = path.read_text(encoding="utf-8")
        meta = parse_meta(text)
        slug = path.stem
        if not meta["title"]:
            warnings.append(f"  {path.name}: missing {{title}}")
            meta["title"] = slug
        if not meta["categories"]:
            warnings.append(f"  {path.name}: missing {{categories}}")
        songs.append({
            "slug": slug,
            "title": meta["title"],
            "subtitle": meta["subtitle"],
            "key": meta["key"],
            "categories": meta["categories"],
            "body": text,
        })

    songs.sort(key=lambda s: s["title"].lower())
    OUT.write_text(json.dumps(songs, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Wrote {len(songs)} songs -> {OUT.relative_to(ROOT)}")
    if warnings:
        print("Warnings:")
        print("\n".join(warnings))


if __name__ == "__main__":
    main()
