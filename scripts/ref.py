#!/usr/bin/env python3
"""Working aid: show my current .cho next to the gliscritti PDF reference,
transposed to my file's key.

Usage:
    py scripts/ref.py <slug> [pdf_title_override] [force_steps]

Auto-detects the transpose interval by comparing the first chord of my file
to the first chord of the PDF reference, unless force_steps is given.
"""
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SONGS = ROOT / "songs"
REF = ROOT / "pdf_reference.txt"

SCALE = ['DO', 'DO#', 'RE', 'RE#', 'MI', 'FA', 'FA#', 'SOL', 'SOL#', 'LA', 'LA#', 'SI']
FLAT = {'DOb': 11, 'REb': 1, 'MIb': 3, 'FAb': 4, 'SOLb': 6, 'LAb': 8, 'SIb': 10}
SHARP = {'DO#': 1, 'RE#': 3, 'MI#': 5, 'FA#': 6, 'SOL#': 8, 'LA#': 10, 'SI#': 0}
NAT = {'DO': 0, 'RE': 2, 'MI': 4, 'FA': 5, 'SOL': 7, 'LA': 9, 'SI': 11}
ROOT_RE = re.compile(r"^(SOL|DO|RE|MI|FA|LA|SI)(#|b)?")


def note_index(note):
    if note in SHARP: return SHARP[note]
    if note in FLAT: return FLAT[note]
    if note in NAT: return NAT[note]
    return None


def transpose_chord(chord, steps):
    if not steps:
        return chord
    parts = []
    for part in chord.split('/'):
        m = ROOT_RE.match(part)
        if not m:
            parts.append(part); continue
        root = m.group(1) + (m.group(2) or '')
        idx = note_index(root)
        if idx is None:
            parts.append(part); continue
        newroot = SCALE[(idx + steps) % 12]
        parts.append(newroot + part[len(root):])
    return '/'.join(parts)


def transpose_text(text, steps):
    def repl(m):
        return '[' + transpose_chord(m.group(1), steps) + ']'
    # transpose bracketed chords
    text = re.sub(r"\[([^\]]+)\]", repl, text)
    # transpose bare chord tokens in reference chord lines (above lyrics)
    def repl_bare(m):
        return transpose_chord(m.group(0), steps)
    return text


def norm(s):
    s = s.replace("’", "'").replace("‘", "'")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", " ", s.upper()).strip()


def first_chord_in_cho(body):
    m = re.search(r"\[((?:SOL|DO|RE|MI|FA|LA|SI)(?:#|b)?[^\]]*)\]", body)
    return m.group(1) if m else None


def first_chord_in_ref(block):
    for line in block.splitlines():
        if line.startswith('###') or line.startswith('@@@'):
            continue
        for tok in line.split():
            tok = tok.replace("Intro:", "").replace("Rit.", "")
            if ROOT_RE.match(tok):
                return tok
    return None


def get_ref_block(title_norm, override=None):
    text = REF.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^@@@ ", text)
    want = norm(override) if override else title_norm
    best = None
    for b in blocks:
        if not b.strip():
            continue
        head = b.splitlines()[0].strip()
        nh = norm(head)
        if nh == want or nh.startswith(want) or want.startswith(nh) and len(nh) >= 4:
            best = b
            break
        if want in nh or nh in want:
            best = best or b
    return best


def transpose_ref_block(block, steps):
    """Transpose bare chord tokens on chord lines (lines above lyrics)."""
    out = []
    for line in block.splitlines():
        if line.startswith('###') or line.startswith('@@@'):
            out.append(line); continue
        # a chord line: mostly chord tokens
        toks = line.split()
        chordish = sum(1 for t in toks if ROOT_RE.match(t.replace("Intro:", "").replace("Rit.", "")))
        if toks and chordish / len(toks) >= 0.5:
            # transpose token-by-token preserving spacing
            def repl(m):
                return transpose_chord(m.group(0), steps)
            out.append(re.sub(r"[A-Za-z#b0-9/]+", lambda m: transpose_chord(m.group(0), steps)
                              if ROOT_RE.match(m.group(0)) else m.group(0), line))
        else:
            out.append(line)
    return "\n".join(out)


def main():
    slug = sys.argv[1]
    override = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].lstrip('-').isdigit() else None
    force = None
    for a in sys.argv[2:]:
        if a.lstrip('-').isdigit():
            force = int(a)
    cho = (SONGS / f"{slug}.cho").read_text(encoding="utf-8")
    m = re.search(r"\{title:\s*(.*?)\}", cho)
    title = m.group(1).strip() if m else slug
    block = get_ref_block(norm(title), override)
    print("========== CURRENT .cho:", slug, "==========")
    print(cho)
    if not block:
        print("!!! NESSUN riscontro nel PDF gliscritti per:", title)
        return
    my_first = first_chord_in_cho(cho)
    pdf_first = first_chord_in_ref(block)
    steps = force
    if steps is None and my_first and pdf_first:
        mi = note_index(ROOT_RE.match(my_first).group(0))
        pi = note_index(ROOT_RE.match(pdf_first).group(0))
        if mi is not None and pi is not None:
            steps = (mi - pi) % 12
            if steps > 6:
                steps -= 12
    steps = steps or 0
    print(f"\n========== PDF REF (my_first={my_first} pdf_first={pdf_first} steps={steps}) ==========")
    print(transpose_ref_block(block, steps))


if __name__ == "__main__":
    main()
