#!/usr/bin/env python3
"""Structure a song's ritornello for {chorus} recall.

  py scripts/wrap_chorus.py <slug> <stanza_index> [stanza_index2 ...]

Wraps the given lyric-stanza(s) (0-based, counting only text stanzas, not
directives) in {start_of_chorus}/{end_of_chorus}, and turns every
{comment: Rit.} / {comment: Rit} into {chorus} so the refrain is reprinted
with chords. Idempotent-ish: refuses if the stanza is already wrapped.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SONGS = ROOT / "songs"


def main():
    slug = sys.argv[1]
    idxs = {int(a) for a in sys.argv[2:]}
    p = SONGS / f"{slug}.cho"
    lines = p.read_text(encoding="utf-8").split("\n")

    # identify text stanzas: contiguous runs of non-blank, non-directive lines
    stanzas = []  # list of (start_i, end_i) inclusive
    i = 0
    while i < len(lines):
        if lines[i].strip() == "" or lines[i].lstrip().startswith("{"):
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].strip() != "" and not lines[j].lstrip().startswith("{"):
            j += 1
        stanzas.append((i, j - 1))
        i = j

    if not idxs:
        for n, (a, b) in enumerate(stanzas):
            print(f"[{n}] {lines[a][:60]}")
        return

    out = []
    wrap_starts = {stanzas[n][0] for n in idxs if n < len(stanzas)}
    wrap_ends = {stanzas[n][1] for n in idxs if n < len(stanzas)}
    for k, line in enumerate(lines):
        if k in wrap_starts:
            out.append("{start_of_chorus}")
        out.append(line)
        if k in wrap_ends:
            out.append("{end_of_chorus}")
    text = "\n".join(out)
    text = re.sub(r"\{comment:\s*Rit\.?[^}]*\}", "{chorus}", text, flags=re.I)
    p.write_text(text, encoding="utf-8")
    print(f"wrapped stanzas {sorted(idxs)} in {slug}; Rit->chorus done")


if __name__ == "__main__":
    main()
