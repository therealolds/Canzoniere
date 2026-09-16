#!/usr/bin/env python3
"""Fill chords into bare lyric lines of a .cho using the gliscritti PDF as the
source, transposed to the file's own key.

Design goals:
  * NEVER touch lines that already have chords (they define the key + were vetted).
  * Only add [chord] to lyric lines that currently have none.
  * Auto-detect the transpose interval by matching my existing chords against
    the PDF at the same lyric position (mode of the intervals).
  * Align on the *full* concatenated lyric text so different line breaks between
    my file and the PDF don't matter. The PDF's broken accents (U+FFFD) and my
    accents/apostrophes are both mapped to a wildcard so they align.

Prints the proposed body to stdout (does not write). Review, then apply.

Usage: py scripts/merge_pdf.py <slug> [pdf_title_override] [force_steps]
"""
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdf_lib as P  # noqa: E402
import pymupdf  # noqa: E402


def text_seg(path):
    """Parse a monospace 'chords-above-lyrics' text file (e.g. the <pre> block
    from accordiespartiti) into pdf_lib-style line dicts. Column index doubles as
    the x-coordinate, so P.merge aligns chords onto the exact character below."""
    lines = Path(path).read_text(encoding="utf-8").replace("\t", "    ").split("\n")
    seg = []
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        words = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", line)]
        toks = [w[2] for w in words]
        chordfrac = sum(1 for t in toks if P.is_chord(t)) / len(toks) if toks else 0
        low = line.strip().lower()
        if low.startswith(("intro", "strofa", "ritornello", "rit.", "rit:", "bridge",
                           "finale", "coda", "ponte")) and chordfrac < 0.5:
            # keep an Intro:/label line's chords if any trail after the label
            kind = "rit" if low.startswith("rit") else "lyric"
        elif chordfrac >= 0.5:
            kind = "chord"
        else:
            kind = "lyric"
        seg.append({"page": 0, "y": 0, "text": line, "kind": kind, "words": words})
    return seg


def external_seg(path):
    """Load a single-page song PDF (e.g. pastoralegiovanile) into pdf_lib-style
    line dicts. Chords are the smaller bold font; classify by size + chord ratio."""
    doc = pymupdf.open(path)
    page = doc[0]
    spans = [(s["bbox"], s["font"], s["size"])
             for b in page.get_text("dict")["blocks"]
             for l in b.get("lines", []) for s in l["spans"]]

    def font_of(w):
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        for bbox, font, size in spans:
            if bbox[0] - 0.5 <= cx <= bbox[2] + 0.5 and bbox[1] - 0.5 <= cy <= bbox[3] + 0.5:
                return font, size
        return "", 0.0

    words = [{"x0": w[0], "y0": w[1], "x1": w[2], "text": w[4], "f": font_of(w)}
             for w in page.get_text("words")]

    # detect a two-column layout: a vertical band in the central third with very
    # few word-starts. These song sheets interleave columns by y otherwise.
    W = page.rect.width
    split = None
    if words:
        import collections
        buckets = collections.Counter(int(w["x0"] // 10) * 10 for w in words)
        lo, hi = int(0.38 * W), int(0.60 * W)
        cand = [(buckets.get(x, 0), x) for x in range(lo, hi, 10)]
        if cand:
            mn = min(cand)
            if mn[0] <= max(2, len(words) * 0.01):   # real gap
                split = mn[1] + 5

    def group_lines(ws):
        ws = sorted(ws, key=lambda w: (round(w["y0"]), w["x0"]))
        out, cur, cy = [], [], None
        for w in ws:
            if cy is None or abs(w["y0"] - cy) <= 4:
                cur.append(w); cy = w["y0"] if cy is None else cy
            else:
                out.append(cur); cur, cy = [w], w["y0"]
        if cur:
            out.append(cur)
        return out

    if split:
        left = [w for w in words if w["x0"] < split]
        right = [w for w in words if w["x0"] >= split]
        groups = group_lines(left) + group_lines(right)
    else:
        groups = group_lines(words)

    seg = []
    for g in groups:
        g.sort(key=lambda w: w["x0"])
        # minor chords are written "Mi -" (space before dash): glue a lone dash
        # onto the preceding note token so conv_chord reads it as minor.
        glued = []
        for w in g:
            if (w["text"] in ("-", "–", "—", "‑") and glued
                    and re.match(r"^(SOL|DO|RE|MI|FA|LA|SI)", glued[-1]["text"], re.I)):
                glued[-1] = {**glued[-1], "text": glued[-1]["text"] + "-", "x1": w["x1"]}
            else:
                glued.append(w)
        g = glued
        toks = [w["text"] for w in g]
        text = " ".join(toks)
        if not text.strip():
            continue
        maxsz = max((f[1] for w in g for f in [w["f"]]), default=12)
        chordfrac = sum(1 for t in toks if P.is_chord(t)) / len(toks) if toks else 0
        if maxsz >= 16:
            kind = "title"
        elif chordfrac >= 0.5 or (maxsz < 10.5 and chordfrac > 0):
            kind = "chord"
        elif re.match(r"^\(?Rit", text, re.I):
            kind = "rit"
        else:
            kind = "lyric"
        seg.append({"page": 0, "y": g[0]["y0"], "text": text, "kind": kind,
                    "words": [(w["x0"], w["x1"], w["text"]) for w in g]})
    return seg

ROOT = Path(__file__).resolve().parent.parent
SONGS = ROOT / "songs"

SCALE = ['DO', 'DO#', 'RE', 'RE#', 'MI', 'FA', 'FA#', 'SOL', 'SOL#', 'LA', 'LA#', 'SI']
FLAT = {'DOb': 11, 'REb': 1, 'MIb': 3, 'FAb': 4, 'SOLb': 6, 'LAb': 8, 'SIb': 10}
SHARP = {'DO#': 1, 'RE#': 3, 'MI#': 5, 'FA#': 6, 'SOL#': 8, 'LA#': 10, 'SI#': 0}
NAT = {'DO': 0, 'RE': 2, 'MI': 4, 'FA': 5, 'SOL': 7, 'LA': 9, 'SI': 11}
ROOT_RE = re.compile(r"^(SOL|DO|RE|MI|FA|LA|SI)(#|b)?")


def nidx(root):
    return SHARP.get(root, FLAT.get(root, NAT.get(root)))


def transpose_chord(chord, steps):
    if not steps:
        return chord
    parts = []
    for part in chord.split('/'):
        m = ROOT_RE.match(part)
        if not m:
            parts.append(part); continue
        root = m.group(1) + (m.group(2) or '')
        i = nidx(root)
        if i is None:
            parts.append(part); continue
        parts.append(SCALE[(i + steps) % 12] + part[len(root):])
    return '/'.join(parts)


SHARP_TO_FLAT = {"DO#": "REb", "RE#": "MIb", "FA#": "SOLb", "SOL#": "LAb", "LA#": "SIb"}


def respell_flats(text, kept_chords):
    """If the song's existing chords use flats (and not sharps), spell accidentals
    in the whole file as flats so filled chords match (LA# -> SIb)."""
    flats = sum(kept_chords.count(f) for f in ("SIb", "MIb", "LAb", "REb", "SOLb", "b]"))
    sharps = len(re.findall(r"(?:DO|RE|FA|SOL|LA)#", kept_chords))
    if flats == 0 or sharps > flats:
        return text
    def repl(m):
        inner = m.group(1)
        for sh, fl in SHARP_TO_FLAT.items():
            inner = re.sub(re.escape(sh), fl, inner)
        return f"[{inner}]"
    return re.sub(r"\[([^\]]+)\]", repl, text)


def wildcard(s):
    """Normalize for fuzzy alignment: lowercase, accents/apostrophes/U+FFFD -> '?'."""
    out = []
    for ch in s:
        if ch == '�' or ch in "àèéìòùáíóúâêîôûäëïöü'’‘`":
            out.append('?')
        else:
            d = unicodedata.normalize('NFD', ch)
            base = ''.join(c for c in d if unicodedata.category(c) != 'Mn')
            out.append(base.lower())
    return ''.join(out)


# ---- build PDF inline stream -------------------------------------------------
def parse_inline(inline):
    """Split '[DO]ciao [RE]mondo' -> (plaintext, [(pos,chord)])."""
    plain = ""
    chords = []
    last = 0
    for m in re.finditer(r"\[([^\]]*)\]", inline):
        plain += inline[last:m.start()]
        tok = m.group(1)
        if ROOT_RE.match(tok):
            chords.append((len(plain), tok))
        last = m.end()
    plain += inline[last:]
    return plain, chords


def pdf_stream(block_lines):
    text = ""
    chords = []
    i, n = 0, len(block_lines)
    while i < n:
        ln = block_lines[i]
        if ln["kind"] in ("title", "section"):
            i += 1; continue
        if ln["kind"] == "chord":
            nxt = block_lines[i + 1] if i + 1 < n else None
            if nxt and nxt["kind"] in ("lyric", "rit"):
                inline = P.merge(ln, nxt)
                plain, cs = parse_inline(inline)
                plain = re.sub(r"\bRit\.?\b", "", plain)
                base = len(text) + (1 if text and not text.endswith("\n") else 0)
                if text and not text.endswith("\n"):
                    text += "\n"
                text += plain
                for pos, ch in cs:
                    chords.append((base + pos, ch))
                i += 2; continue
            i += 1; continue
        raw = re.sub(r"\bRit\.?\b", "", ln["text"]).strip()
        if raw:
            if text and not text.endswith("\n"):
                text += "\n"
            text += raw
        i += 1
    return text, chords


# ---- my .cho model -----------------------------------------------------------
def my_lines(body, replace=False):
    """Return list of dicts describing each source line. In replace mode every
    lyric line is refillable (existing chords are discarded, lyrics kept)."""
    res = []
    for raw in body.split("\n"):
        line = raw.rstrip()
        if line.strip() == "":
            res.append({"kind": "blank", "raw": raw})
        elif re.match(r"^\{", line):
            res.append({"kind": "dir", "raw": line})
        else:
            plain, cs = parse_inline(line)
            fillable = replace or len(cs) == 0
            res.append({"kind": "lyric", "raw": plain if replace else line,
                        "plain": plain, "chords": [] if replace else cs,
                        "fillable": fillable})
    return res


def main():
    slug = sys.argv[1]
    override = None
    force = None
    pdf_path = None
    web_path = None
    args = sys.argv[2:]
    for k, a in enumerate(args):
        if a == "--pdf":
            pdf_path = args[k + 1]
        elif a == "--web":
            web_path = args[k + 1]
        elif a.startswith("--"):
            continue
        elif k > 0 and args[k - 1] in ("--pdf", "--web"):
            continue
        elif a.lstrip('-').isdigit():
            force = int(a)
        else:
            override = a

    cho = (SONGS / f"{slug}.cho").read_text(encoding="utf-8")
    mt = re.search(r"\{title:\s*(.*?)\}", cho)
    title = mt.group(1).strip() if mt else slug

    if pdf_path:
        seg = external_seg(pdf_path)
    elif web_path:
        seg = text_seg(web_path)
    else:
        lines = P.load_lines()
        seg = P.find_song(lines, override or title)
    if not seg:
        print(f"!!! PDF: nessun riscontro per {title!r}")
        return
    ptext, pchords = pdf_stream(seg)

    # split my file into header (directives before first lyric) and body lines
    REPLACE = "--replace" in sys.argv
    ml = my_lines(cho, replace=REPLACE)

    # Build M text from lyric lines, with position map -> (line_index, char)
    M = ""
    posmap = []  # M index -> (li, char)
    for li, d in enumerate(ml):
        if d["kind"] != "lyric":
            continue
        if M:
            M += "\n"; posmap.append((li, -1))
        for ci, ch in enumerate(d["plain"]):
            posmap.append((li, ci))
            M += ch

    # lyric-overlap gate: refuse to merge a different song matched by a loose title
    def sig_words(s):
        return {w for w in re.findall(r"[a-z?]{4,}", wildcard(s))}
    mw, pw = sig_words(M), sig_words(ptext)
    overlap = len(mw & pw) / len(mw) if mw else 0.0
    if overlap < 0.35 and "--force" not in sys.argv:
        print(f"!!! OVERLAP BASSO ({overlap:.2f}) tra il mio testo e il PDF -> "
              f"probabile canto diverso. Salto. (usa --force per ignorare)")
        sys.stderr.write(f"[overlap={overlap:.2f} ABORT]\n")
        return

    # align
    a, b = wildcard(ptext), wildcard(M)
    sm = SequenceMatcher(None, a, b, autojunk=False)
    # map P index -> M index
    p2m = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal",):
            for k in range(i2 - i1):
                p2m[i1 + k] = j1 + k
        elif tag == "replace":
            for k in range(i2 - i1):
                p2m[i1 + k] = j1 + min(k, max(0, j2 - j1 - 1))
        elif tag == "delete":
            for k in range(i2 - i1):
                p2m[i1 + k] = j1
        # insert: nothing maps

    # detect steps by chord-SET overlap: pick the transposition of the PDF chords
    # whose root set best covers my existing chord roots (robust to different
    # harmonisations / line breaks). Tie-break toward the smallest shift.
    my_roots = []
    for m in re.finditer(r"\[([^\]]+)\]", cho):   # from ORIGINAL chords (replace strips them from ml)
        rm = ROOT_RE.match(m.group(1))
        if rm:
            my_roots.append(nidx(rm.group(0)))
    pdf_roots = [nidx(ROOT_RE.match(c).group(0)) for (_, c) in pchords if ROOT_RE.match(c)]
    best_score = 0.0
    steps = force
    if steps is None:
        best = 0
        for st in list(range(0, 7)) + list(range(-1, -6, -1)):
            shifted = {(r + st) % 12 for r in pdf_roots}
            score = sum(1 for r in my_roots if r in shifted) / len(my_roots) if my_roots else 0
            if score > best_score + 1e-9:
                best_score, best = score, st
        steps = best
    votes = f"score={best_score:.2f}"

    # place PDF chords into fillable lines
    inserts = {}  # li -> list of (char, chord)
    for (ppos, pch) in pchords:
        mi = p2m.get(ppos)
        if mi is None or mi >= len(posmap):
            continue
        li, ci = posmap[mi]
        if ci < 0:
            # landed on a newline join; push to next char
            if mi + 1 < len(posmap):
                li, ci = posmap[mi + 1]
        d = ml[li]
        if d["kind"] != "lyric" or not d["fillable"]:
            continue
        inserts.setdefault(li, []).append((ci, transpose_chord(pch, steps)))

    # render
    out = []
    for li, d in enumerate(ml):
        if d["kind"] in ("blank", "dir"):
            out.append(d["raw"]); continue
        if li not in inserts:
            out.append(d["raw"]); continue
        plain = d["plain"]
        ins = sorted(inserts[li], key=lambda t: t[0])
        # collapse chords stacked at the same char (line-break artifact: a
        # trailing chord of the previous PDF line maps onto our line start) ->
        # keep the last one (the one actually on the syllable); dedupe repeats.
        cleaned = []
        for ci, ch in ins:
            if cleaned and ci == cleaned[-1][0]:
                cleaned[-1] = (ci, ch)          # same position: keep later chord
                continue
            if cleaned and ci - cleaned[-1][0] <= 1 and cleaned[-1][1] == ch:
                continue                         # adjacent identical: drop repeat
            cleaned.append((ci, ch))
        res, last = "", 0
        for ci, ch in cleaned:
            ci = max(0, min(len(plain), ci))
            res += plain[last:ci] + f"[{ch}]"
            last = ci
        res += plain[last:]
        out.append(res)

    # collapse runs of >=2 chords stacked right before lyric text (a line-break
    # artifact) down to the last chord (the one on the syllable). End-of-line
    # turnarounds like "...mo.[FA][DO][MI]\n" are followed by \n, not \w, so kept.
    def collapse(m):
        chords = re.findall(r"\[[^\]]+\]", m.group(0))
        return chords[-1]
    out = [re.sub(r"(?:\[[^\]]+\]){2,}(?=[^\s\[])", collapse, line)
           if not re.match(r"^\{", line) else line for line in out]

    result = "\n".join(out)
    # match accidental spelling to the song's key (flat keys -> flats)
    kept = " ".join(re.findall(r"\[[^\]]+\]", cho))
    result = respell_flats(result, kept)

    sys.stderr.write(f"[steps={steps} votes={votes}]\n")
    if "--write" in sys.argv:
        (SONGS / f"{slug}.cho").write_text(result if result.endswith("\n") else result + "\n",
                                           encoding="utf-8")
        sys.stderr.write(f"[written songs/{slug}.cho]\n")
    else:
        print(result)


if __name__ == "__main__":
    main()
