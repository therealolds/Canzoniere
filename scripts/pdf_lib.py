#!/usr/bin/env python3
"""Helper to pull chord/lyric layout for a single song out of the gliscritti
'Libretto dei canti' PDF (lib_canti_chit.pdf).

The PDF distinguishes content by font:
  * song title      -> Times-Bold      size ~12, UPPERCASE
  * chord line      -> Times-Bold      size ~11 (chords sit above the lyric)
  * lyric line      -> Times-Italic    size ~12
  * 'Rit' label     -> Times-BoldItalic
  * section header  -> Times-Bold      size >=16 ("CANTI PER LA LITURGIA")

Chords use '-' for minor (La- = LAm, Do#- = DO#m). We convert to the site's
Italian notation (DO RE MI FA SOL LA SI, minor = 'm').

Lyric text in the PDF has broken accents/apostrophes (all -> U+FFFD), so this
module is only trusted for CHORDS and their horizontal position; clean lyrics
come from the existing songs/*.cho files.
"""
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "lib_canti_chit.pdf"

LINE_TOL = 4.0

# ---- chord recognition + conversion -----------------------------------------
_ROOT = r"(?:DO|RE|MI|FA|SOL|LA|SI|Do|Re|Mi|Fa|Sol|La|Si)"
_ACC = r"(?:#|b)?"
_QUAL = r"(?:maj7|maj|sus2|sus4|sus|dim|add9|add|m|-|\+|7|6|9|11|13|4|2|°)*"
CHORD_RE = re.compile(rf"^{_ROOT}{_ACC}{_QUAL}(?:/{_ROOT}{_ACC})?$")

_NOTE_MAP = {"DO": "DO", "RE": "RE", "MI": "MI", "FA": "FA", "SOL": "SOL", "LA": "LA", "SI": "SI"}
_ROOT_ONE = re.compile(r"^(SOL|DO|RE|MI|FA|LA|SI)(#|b)?", re.I)


def _dashnorm(s):
    return s.replace("–", "-").replace("—", "-").replace("‑", "-")


def is_chord(tok):
    t = _dashnorm(tok.replace("♯", "#").replace("♭", "b")).strip("()[].,:;")
    return len(t) >= 2 and bool(CHORD_RE.match(t))


def conv_chord(tok):
    """'La-' -> 'LAm', 'Do#-7' -> 'DO#m7', 'Sol/Si' -> 'SOL/SI'."""
    raw = _dashnorm(tok.replace("♯", "#").replace("♭", "b")).strip()
    lead = "".join(c for c in raw if c in "([")
    trail = "".join(c for c in reversed(raw) if c in ")].,:;")[::-1]
    core = raw[len(lead):len(raw) - len(trail)] if trail else raw[len(lead):]

    def conv_part(part):
        m = _ROOT_ONE.match(part)
        if not m:
            return part
        root = (m.group(1).upper()) + (m.group(2) or "")
        rest = part[m.end():]
        # minor: a hyphen right after the root becomes 'm'
        rest = re.sub(r"^-", "m", rest)
        rest = rest.replace("-", "")  # stray hyphens
        return root + rest

    out = "/".join(conv_part(p) for p in core.split("/"))
    return lead + out + trail


# ---- PDF line model ----------------------------------------------------------
def _line_kind(spans_fonts, tokens):
    """Return 'title' | 'chord' | 'rit' | 'lyric' | 'section'."""
    fonts = spans_fonts
    sizes = [sz for _, sz in fonts]
    names = [fn for fn, _ in fonts]
    max_sz = max(sizes) if sizes else 0
    text = " ".join(tokens)
    letters = [c for c in text if c.isalpha()]
    upper = sum(c.isupper() for c in letters) / len(letters) if letters else 0

    if max_sz >= 15:
        return "section"
    bold = any("Bold" in n and "Italic" not in n for n in names)
    italic = any("Italic" in n for n in names)
    chord_frac = sum(1 for t in tokens if is_chord(t)) / len(tokens) if tokens else 0

    if re.match(r"^Rit\b", text, re.I) and len(tokens) <= 2:
        return "rit"
    # chords: small bold, or mostly chord tokens
    if chord_frac >= 0.5 or (bold and not italic and max_sz <= 11.5 and upper < 0.9 and chord_frac > 0):
        return "chord"
    if bold and not italic and upper >= 0.7 and 0 < len(text) <= 60 and len(tokens) <= 10:
        return "title"
    return "lyric"


def load_lines():
    doc = pymupdf.open(PDF)
    all_lines = []
    for pno in range(doc.page_count):
        page = doc[pno]
        spans = []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    spans.append((s["bbox"], s["font"], s["size"]))

        def font_of(w):
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            for (bbox, font, size) in spans:
                if bbox[0] - 0.5 <= cx <= bbox[2] + 0.5 and bbox[1] - 0.5 <= cy <= bbox[3] + 0.5:
                    return font, size
            return "", 0.0

        words = [{"x0": w[0], "y0": w[1], "x1": w[2], "text": w[4], "f": font_of(w)}
                 for w in page.get_text("words")]
        words.sort(key=lambda w: (round(w["y0"]), w["x0"]))
        # group into visual lines
        cur, cur_y = [], None
        groups = []
        for w in words:
            if cur_y is None or abs(w["y0"] - cur_y) <= LINE_TOL:
                cur.append(w); cur_y = w["y0"] if cur_y is None else cur_y
            else:
                groups.append(cur); cur, cur_y = [w], w["y0"]
        if cur:
            groups.append(cur)
        for g in groups:
            g.sort(key=lambda w: w["x0"])
            toks = [w["text"] for w in g]
            text = " ".join(toks)
            if re.fullmatch(r"[-\s\d]+", text):   # page numbers "- 5 -"
                continue
            kind = _line_kind([w["f"] for w in g], toks)
            all_lines.append({
                "page": pno, "y": g[0]["y0"], "text": text, "kind": kind,
                "words": [(w["x0"], w["x1"], w["text"]) for w in g],
            })
    return all_lines


def _norm(s):
    s = s.replace("’", "'").replace("‘", "'")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", " ", s.upper()).strip()


def find_song(lines, title, occurrence=1):
    """Return the slice of lines for `title` (from its heading to the next heading)."""
    nt = _norm(title)
    titles = [i for i, ln in enumerate(lines) if ln["kind"] == "title"]
    hits = []
    for i in titles:
        nn = _norm(lines[i]["text"])
        if not nn:
            continue
        # exact, or one is a prefix of the other covering most of the longer one
        if nn == nt:
            hits.append(i)
        elif (nn.startswith(nt) or nt.startswith(nn)):
            short, long = sorted((len(nn), len(nt)))
            if short / long >= 0.7 and short >= 4:
                hits.append(i)
    if not hits:
        return None
    start = hits[min(occurrence - 1, len(hits) - 1)]
    # end = next title
    end = len(lines)
    for i in titles:
        if i > start:
            end = i
            break
    return lines[start:end]


# ---- chord/lyric merge -------------------------------------------------------
def merge(chord_line, lyric_line):
    """Insert [chord] tokens into the lyric string at x-aligned char offsets."""
    parts, anchors, pos = [], [], 0
    for (x0, x1, txt) in lyric_line["words"]:
        if parts:
            pos += 1
        anchors.append((x0, x1, pos, len(txt)))
        parts.append(txt)
        pos += len(txt)
    lyric = " ".join(parts)

    inserts = []
    for (cx0, cx1, ctxt) in chord_line["words"]:
        chord = conv_chord(ctxt)
        idx = None
        for (x0, x1, cs, wl) in anchors:
            if abs(cx0 - x0) <= 3.5:
                idx = cs; break
        if idx is None:
            if anchors and cx0 <= anchors[0][0]:
                idx = 0
            else:
                for (x0, x1, cs, wl) in anchors:
                    if x0 <= cx0 <= x1:
                        idx = cs + int((cx0 - x0) / max(1.0, (x1 - x0)) * wl); break
                if idx is None:
                    after = [a for a in anchors if a[0] > cx0]
                    idx = after[0][2] if after else len(lyric)
        inserts.append((idx, f"[{chord}]"))
    inserts.sort(key=lambda t: t[0])
    out, last = [], 0
    for idx, tag in inserts:
        idx = max(0, min(len(lyric), idx))
        out.append(lyric[last:idx]); out.append(tag); last = idx
    out.append(lyric[last:])
    return "".join(out)


def render_reference(seg):
    """Human-readable chords-above-lyrics dump for a song slice."""
    out = []
    for ln in seg:
        if ln["kind"] == "chord":
            # rebuild spaced chord line using x positions (approx monospace)
            s = ""
            for (x0, x1, txt) in ln["words"]:
                col = int((x0 - 50) / 5.2)
                if col < len(s):
                    col = len(s) + 1
                s += " " * (col - len(s)) + conv_chord(txt)
            out.append(s)
        elif ln["kind"] == "section":
            continue
        elif ln["kind"] == "title":
            out.append(f"### {ln['text']}")
        else:
            out.append(ln["text"])
    return "\n".join(out)


if __name__ == "__main__":
    title = sys.argv[1] if len(sys.argv) > 1 else ""
    occ = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    lines = load_lines()
    seg = find_song(lines, title, occ)
    if not seg:
        print(f"NOT FOUND: {title}")
        sys.exit(1)
    print(render_reference(seg))
