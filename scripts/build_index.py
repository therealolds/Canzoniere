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

# What the site draws as a chord (mirrors looksLikeChord() in src/chordpro.js)...
SITE_CHORD_RE = re.compile(r"^(?:SOL|DO|RE|MI|FA|LA|SI)(?:#|b)?")
# ...and what a well-formed one looks like: LAm, FA#m7, DO7+, SIb, RE/FA#, LA4/7.
NOTE = r"(?:SOL|DO|RE|MI|FA|LA|SI)(?:#|b)?"
CHORD_RE = re.compile(
    rf"^{NOTE}(?:maj|min|dim|aug|sus|add|m|M|\d|\+|-|°|[#b]\d|\([#b]?\d+\))*(?:/(?:{NOTE}|\d+))?$"
)
# A chord the site won't recognise: wrong case (La, sol7) or English names (E, Am).
LOOSE_CHORD_RE = re.compile(
    r"^(?:do|re|mi|fa|sol|la|si|[a-g])(?:#|b)?(?:m|maj|dim|sus|add|\d|\+)*$", re.I
)
# Bracketed marks that are meant to be printed as they are.
MARKS = {"*", "§", "𝄋"}


def lint_brackets(text):
    """Yield (line number, message) for [...] the site would draw wrongly:
    chord fragments printed in the lyrics, or chords that aren't valid.
    Bracketed words ([x2], [solo], [fine]) are taken as deliberate notes."""
    for n, line in enumerate(text.splitlines(), 1):
        if DIRECTIVE_RE.match(line):
            continue
        if line.count("[") != line.count("]"):
            yield n, "unbalanced [ ]"
        as_text, malformed = [], []
        for tok in re.findall(r"\[([^\]]*)\]", line):
            if tok in MARKS:
                continue
            if SITE_CHORD_RE.match(tok) and not re.search(r"\s", tok):
                if not CHORD_RE.match(tok):
                    malformed.append(f"[{tok}]")
            elif (SITE_CHORD_RE.match(tok) or "[" in tok or len(tok) < 2
                  or not re.search(r"[^\W\d_]", tok) or LOOSE_CHORD_RE.match(tok)):
                as_text.append(f"[{tok}]")
        if as_text:
            yield n, f"{' '.join(as_text)} printed in the lyrics as text (broken chord?)"
        if malformed:
            yield n, f"{' '.join(malformed)} drawn as a chord, but not a valid one"


# A comment that means "sing the chorus here" (mirrors RIT_RE in src/chordpro.js).
RIT_RE = re.compile(r"^\(?\s*rit(?:ornello)?\b\.?\s*(?:x\s*\d+|\(\s*x\s*\d+\s*\)|\([^)]*\))?\s*\)?\s*:?\s*$", re.I)


def lint_chorus(text):
    """Yield (line number, message) for chorus repeats the site can't reprint:
    a Rit. comment or {chorus} in a song whose chorus isn't marked, or a Rit.
    left at the end of a lyric line."""
    lines = text.splitlines()
    marked = any((m := DIRECTIVE_RE.match(l)) and m.group(1).lower() in ("start_of_chorus", "soc") for l in lines)
    for n, line in enumerate(lines, 1):
        m = DIRECTIVE_RE.match(line)
        if m:
            name, value = m.group(1).lower(), (m.group(2) or "").strip()
            repeat = name == "chorus" or (name in ("comment", "c") and RIT_RE.match(value))
            if repeat and not marked:
                yield n, "chorus repeat, but no {start_of_chorus}...{end_of_chorus} to reprint"
        elif re.search(r"\S\s+Rit\.?\s*$", line):
            yield n, "Rit. at the end of a lyric line: put it on its own {comment: Rit.} line"


def parse_meta(text):
    meta = {"title": "", "subtitle": "", "key": "", "categories": [], "explicit": False}
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
        elif name == "explicit":
            meta["explicit"] = True
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
        for n, msg in [*lint_brackets(text), *lint_chorus(text)]:
            warnings.append(f"  {path.name}:{n}: {msg}")
        songs.append({
            "slug": slug,
            "title": meta["title"],
            "subtitle": meta["subtitle"],
            "key": meta["key"],
            "categories": meta["categories"],
            "explicit": meta["explicit"],
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
