#!/usr/bin/env python3
"""Render a .cho the way the site does: chords on a line above the lyrics.
Mirrors src/chordpro.js songToText(chords=true) closely enough for QA.

Usage: py scripts/preview.py songs/i-cieli-narrano.cho
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ROOT_RE = re.compile(r"^(SOL|DO|RE|MI|FA|LA|SI)(#|b)?")


def looks_like_chord(tok):
    return bool(ROOT_RE.match(tok)) and not re.search(r"\s", tok)


def parse_line(line):
    segs, last, pending = [], 0, ""
    for m in re.finditer(r"\[([^\]]*)\]", line):
        text = line[last:m.start()]
        if text or pending:
            segs.append((pending, text))
        inner = m.group(1)
        if looks_like_chord(inner):
            pending = inner
        else:
            if inner:
                segs.append(("", f"[{inner}]"))
            pending = ""
        last = m.end()
    tail = line[last:]
    if tail or pending:
        segs.append((pending, tail))
    if not segs:
        segs = [("", "")]
    return segs


def render(text):
    out = []
    choruses = {}
    last_key = None
    cur = None
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if line.strip() == "":
            out.append("")
            continue
        d = re.match(r"^\{\s*([^:}]+?)\s*(?::\s*(.*?)\s*)?\}$", line)
        if d:
            name = d.group(1).lower()
            val = d.group(2) or ""
            if name in ("title", "t"):
                out.append(val.upper())
            elif name in ("subtitle", "st"):
                out.append(f"({val})")
            elif name in ("start_of_chorus", "soc"):
                cur = {"key": val or "__d__", "lines": []}
            elif name in ("end_of_chorus", "eoc"):
                if cur:
                    choruses[cur["key"]] = cur["lines"]
                    last_key = cur["key"]
                    cur = None
            elif name == "chorus":
                key = val or last_key or "__d__"
                out.append("Rit.")
                for segs in choruses.get(key, []):
                    out.append(_fmt(segs))
                if not choruses.get(key):
                    out.append("(Rit. non definito!)")
            elif name in ("comment", "c"):
                out.append(f"# {val}")
            continue
        segs = parse_line(line)
        out.append(_fmt(segs))
        if cur is not None:
            cur["lines"].append(segs)
    return "\n".join(out)


def _fmt(segs):
    lyric, chord_line, has = "", "", False
    for chord, text in segs:
        if chord:
            has = True
            if len(chord_line) < len(lyric):
                chord_line += " " * (len(lyric) - len(chord_line))
            chord_line += chord + " "
        lyric += text
    res = []
    if has:
        res.append(chord_line.rstrip())
    res.append(lyric)
    return "\n".join(res)


if __name__ == "__main__":
    p = Path(sys.argv[1])
    print(render(p.read_text(encoding="utf-8")))
