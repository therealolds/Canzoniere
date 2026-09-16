#!/usr/bin/env python3
"""Classify each preghiera song by chord coverage: empty / partial / complete.

partial  = has chord markers somewhere, but at least one *text* stanza (a run of
           lyric lines, not a directive/chorus recall) has zero chords.
empty    = no chord markers at all.
complete = every text stanza carries chords (repeats handled via {chorus}).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SONGS = ROOT / "songs"

CHORD = re.compile(r"\[(?:SOL|DO|RE|MI|FA|LA|SI)(?:#|b)?[^\]]*\]")


def stanzas(body):
    """Yield lists of lyric lines, split on blank lines, skipping directives."""
    cur = []
    for raw in body.splitlines():
        line = raw.rstrip()
        if line.strip() == "":
            if cur:
                yield cur; cur = []
            continue
        if re.match(r"^\{", line):          # directive: chorus markers, comments...
            if cur:
                yield cur; cur = []
            continue
        cur.append(line)
    if cur:
        yield cur


def classify(text):
    total_chords = len(CHORD.findall(text))
    if total_chords == 0:
        return "empty", 0, 0
    sts = list(stanzas(text))
    text_stanzas = len(sts)
    bare = sum(1 for st in sts if not any(CHORD.search(l) for l in st))
    if bare == 0:
        return "complete", text_stanzas, bare
    return "partial", text_stanzas, bare


def main():
    cat = sys.argv[1] if len(sys.argv) > 1 else "preghiera"
    rows = {"empty": [], "partial": [], "complete": []}
    for f in sorted(SONGS.glob("*.cho")):
        t = f.read_text(encoding="utf-8")
        m = re.search(r"\{categories:\s*(.*?)\}", t)
        cats = [c.strip() for c in m.group(1).split(",")] if m else []
        if cat not in cats:
            continue
        kind, nst, bare = classify(t)
        rows[kind].append((f.stem, nst, bare))
    for kind in ("empty", "partial", "complete"):
        print(f"===== {kind.upper()} ({len(rows[kind])}) =====")
        for slug, nst, bare in rows[kind]:
            extra = f"  (strofe={nst}, senza-accordi={bare})" if kind == "partial" else ""
            print(f"  {slug}{extra}")


if __name__ == "__main__":
    main()
