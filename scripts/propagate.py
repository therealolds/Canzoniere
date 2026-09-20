#!/usr/bin/env python3
"""Fill bare verses of a .cho by propagating the chord pattern of an existing
chorded verse of the SAME shape (same line count), placing each chord at the
same word index / in-word offset as in the template.

Safe by design:
  * Never touches lines/stanzas that already have chords.
  * Only fills a bare stanza when a chorded template with the identical line
    count exists; otherwise it leaves the stanza alone and reports it as a
    FLAG (needs manual/web sourcing).
  * Detects bare stanzas that merely repeat a chorded chorus and rewrites them
    as {chorus} recalls (wrapping the template chorus in start/end once).

Usage:
  py scripts/propagate.py <slug>            # preview to stdout + status on stderr
  py scripts/propagate.py <slug> --write    # write the file
  py scripts/propagate.py --all             # status report for every partial italiane
"""
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SONGS = ROOT / "songs"
ROOT_RE = re.compile(r"^(SOL|DO|RE|MI|FA|LA|SI)(#|b)?")
CHORD_TOKEN = re.compile(r"\[([^\]]*)\]")


def is_chord_token(tok):
    return bool(ROOT_RE.match(tok))


def norm(s):
    """Fold accents/apostrophes/case for stanza-text comparison."""
    out = []
    for ch in s:
        if ch in "'’‘`":
            continue
        d = unicodedata.normalize("NFD", ch)
        out.append("".join(c for c in d if unicodedata.category(c) != "Mn").lower())
    return re.sub(r"\s+", " ", "".join(out)).strip()


def parse_line(line):
    """'[DO]ciao [RE]mondo' -> (plain, [(char_pos, chord)])."""
    plain = ""
    chords = []
    last = 0
    for m in CHORD_TOKEN.finditer(line):
        plain += line[last:m.start()]
        tok = m.group(1)
        if is_chord_token(tok):
            chords.append((len(plain), tok))
        else:
            plain += f"[{tok}]"                 # keep annotations as text
        last = m.end()
    plain += line[last:]
    return plain, chords


def word_starts(text):
    return [m.start() for m in re.finditer(r"\S+", text)]


def snap_to_word(text, pos):
    """Snap a char position to the start of the word at/after it."""
    starts = word_starts(text)
    if not starts:
        return 0
    best = starts[0]
    for s in starts:
        if s <= pos:
            best = s
        else:
            break
    # if pos is well past this word's start, prefer the next word start when closer
    nxt = next((s for s in starts if s > pos), None)
    if nxt is not None and (nxt - pos) < (pos - best):
        best = nxt
    return best


def transfer_placements(tplain, tchords, bplain):
    """Map template chords (char positions in tplain) onto bplain by proportional
    position, snapping to word starts. Trailing turnaround chords (those after the
    last word of the template) are appended, in order, at the end of bplain."""
    tstarts = word_starts(tplain)
    last_word = tstarts[-1] if tstarts else 0
    body, trailing = [], []
    for pos, ch in tchords:
        if pos > last_word + 0  and pos >= len(tplain.rstrip()):
            trailing.append(ch)
        else:
            body.append((pos, ch))
    out = []
    tlen = max(1, len(tplain.rstrip()))
    for pos, ch in body:
        frac = min(1.0, pos / tlen)
        target = int(round(frac * len(bplain.rstrip())))
        out.append((snap_to_word(bplain, target), ch))
    return out, trailing


# ---- stanza model ------------------------------------------------------------
def segments(body):
    """Yield ('dir', raw) | ('blank', raw) | ('stanza', [line_dicts])."""
    cur = []
    for raw in body.split("\n"):
        line = raw.rstrip()
        if line.strip() == "":
            if cur:
                yield ("stanza", cur); cur = []
            yield ("blank", raw)
        elif line.startswith("{"):
            if cur:
                yield ("stanza", cur); cur = []
            yield ("dir", line)
        else:
            plain, placed = parse_line(line)
            cur.append({"raw": line, "plain": plain, "placed": placed})
    if cur:
        yield ("stanza", cur)


def stanza_has_chords(st):
    return any(l["placed"] for l in st)


def stanza_text(st):
    return norm(" ".join(l["plain"] for l in st))


def render_placed(plain, placements):
    """placements: list of (char_pos, chord). Insert into plain, deduping chords
    stacked at the same position (keep the later one) and adjacent repeats."""
    ins = sorted(placements, key=lambda t: t[0])
    cleaned = []
    for ci, ch in ins:
        if cleaned and cleaned[-1][0] == ci:
            cleaned[-1] = (ci, ch)          # same spot: keep later chord
            continue
        cleaned.append((ci, ch))
    res, last = "", 0
    for ci, ch in cleaned:
        ci = max(last, min(len(plain), ci))
        res += plain[last:ci] + f"[{ch}]"
        last = ci
    res += plain[last:]
    return res


def propagate(slug):
    cho = (SONGS / f"{slug}.cho").read_text(encoding="utf-8")
    # keep header directives; operate on the whole body via segments
    segs = list(segments(cho))
    stanzas = [(i, s[1]) for i, s in enumerate(segs) if s[0] == "stanza"]

    templates = [(i, st) for (i, st) in stanzas if stanza_has_chords(st)]
    # Only a FULLY chorded verse (every line carries a chord) is a safe pattern
    # to stamp onto a bare verse. A half-chorded verse would propagate its gaps.
    full_templates = [(i, st) for (i, st) in templates if all(l["placed"] for l in st)]
    bare = [(i, st) for (i, st) in stanzas if not stanza_has_chords(st)]

    flags = []
    filled = 0
    chorus_recalls = 0

    # 1) chorus recall: a bare stanza whose text matches a chorded template
    template_by_text = {}
    for (i, st) in templates:
        template_by_text.setdefault(stanza_text(st), (i, st))

    chorus_template_idx = None
    seg_replace = {}   # segment index -> new list of raw lines (or None to drop)

    for (bi, bst) in bare:
        btext = stanza_text(bst)
        if btext in template_by_text:
            ti, tst = template_by_text[btext]
            chorus_template_idx = ti
            seg_replace[bi] = ["{chorus}"]
            chorus_recalls += 1
            continue
        # 2) verse propagation: same line count as some FULL template
        cand = [t for t in full_templates if len(t[1]) == len(bst)]
        if not cand:
            flags.append(f"stanza@seg{bi} ({len(bst)} righe) senza template completo di pari lunghezza")
            continue
        _, tst = cand[0]
        newlines = []
        for tline, bline in zip(tst, bst):
            placements, trailing = transfer_placements(tline["plain"], tline["placed"], bline["plain"])
            line = render_placed(bline["plain"], placements)
            if trailing:
                line = line + "".join(f"[{c}]" for c in trailing)
            newlines.append(line)
        seg_replace[bi] = newlines
        filled += 1

    # wrap the chorus template in start/end if we created any {chorus} recall
    if chorus_recalls and chorus_template_idx is not None:
        st = segs[chorus_template_idx][1]
        wrapped = ["{start_of_chorus}"] + [l["raw"] for l in st] + ["{end_of_chorus}"]
        seg_replace[chorus_template_idx] = wrapped

    # render
    out = []
    for i, (kind, payload) in enumerate(segs):
        if i in seg_replace:
            out.extend(seg_replace[i])
        elif kind == "stanza":
            out.extend(l["raw"] for l in payload)
        else:
            out.append(payload)
    result = "\n".join(out)
    result = result.rstrip("\n") + "\n"
    cls = classify(result)
    status = f"{cls:8} filled={filled} chorus={chorus_recalls} flags={len(flags)}"
    return result, status, flags, cls


CHORD_RE = re.compile(r"\[(?:SOL|DO|RE|MI|FA|LA|SI)(?:#|b)?[^\]]*\]")


def classify(text):
    """empty / partial / complete, mirroring scripts/audit.py."""
    if not CHORD_RE.search(text):
        return "empty"
    cur, bare_ct, total = [], 0, 0

    def flush():
        nonlocal bare_ct, total
        if cur:
            total += 1
            if not any(CHORD_RE.search(l) for l in cur):
                bare_ct += 1

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip() == "" or line.startswith("{"):
            flush(); cur.clear()
            continue
        cur.append(line)
    flush()
    return "complete" if bare_ct == 0 else "partial"


def partial_slugs(cat="italiane"):
    CHORD = re.compile(r"\[(?:SOL|DO|RE|MI|FA|LA|SI)(?:#|b)?[^\]]*\]")
    out = []
    for f in sorted(SONGS.glob("*.cho")):
        t = f.read_text(encoding="utf-8")
        m = re.search(r"\{categories:\s*(.*?)\}", t)
        cats = [c.strip() for c in m.group(1).split(",")] if m else []
        if cat not in cats:
            continue
        out.append(f.stem)
    return out


def main():
    if sys.argv[1] == "--all":
        buckets = {"complete": [], "partial": [], "empty": []}
        for slug in partial_slugs():
            try:
                _, status, flags, cls = propagate(slug)
            except Exception as e:  # noqa
                print(f"{slug:45} ERROR {e}"); continue
            buckets.setdefault(cls, []).append((slug, status, flags))
        for cls in ("complete", "partial", "empty"):
            rows = buckets[cls]
            print(f"\n===== diventa {cls.upper()} ({len(rows)}) =====")
            for slug, status, flags in rows:
                fl = ("  !! " + "; ".join(flags)) if flags else ""
                print(f"  {slug:45} {status}{fl}")
        return

    slug = sys.argv[1]
    result, status, flags, cls = propagate(slug)
    sys.stderr.write(f"[{status}]\n")
    for fl in flags:
        sys.stderr.write(f"  FLAG: {fl}\n")
    if "--write" in sys.argv:
        (SONGS / f"{slug}.cho").write_text(result, encoding="utf-8")
        sys.stderr.write(f"[written songs/{slug}.cho]\n")
    else:
        print(result)


if __name__ == "__main__":
    main()
