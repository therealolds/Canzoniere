#!/usr/bin/env python3
"""Restore a song's ORIGINAL .cho body from songs.json (which still holds the
pre-edit bodies until build_index.py is re-run). Safety net for re-doing a merge.

  py scripts/restore.py <slug> [<slug> ...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SONGS = ROOT / "songs"
# prefer the pristine pre-edit backup if present
src = ROOT / "songs.original.json"
if not src.exists():
    src = ROOT / "songs.json"
data = json.loads(src.read_text(encoding="utf-8"))
by_slug = {s["slug"]: s for s in data}

for slug in sys.argv[1:]:
    if slug not in by_slug:
        print(f"!!! {slug} non in songs.json"); continue
    (SONGS / f"{slug}.cho").write_text(by_slug[slug]["body"], encoding="utf-8")
    print(f"restored songs/{slug}.cho from songs.json backup")
