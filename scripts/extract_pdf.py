#!/usr/bin/env python3
"""Extract every song from CANZONIERE_DEFINITIVO.pdf into ChordPro (.cho) files.

The PDF uses distinct fonts we can key off:
  * titles  -> bold  (Arial-BoldMT)
  * chords  -> italic (Arial-ItalicMT)
  * lyrics  -> regular (ArialMT)
  * section headers -> large bold-italic ("Canzoni per la preghiera", ...)

So song boundaries come from bold headings (catches songs missing from the
truncated ELENCO), chord lines from italic, and each chord is dropped back onto
the syllable it sits above using word coordinates. ELENCO.txt, where it matches,
supplies clean title/artist/category; otherwise the category comes from the
section the page belongs to.

Best-effort automated pass — spot-check chord placement. Run:
    py scripts/extract_pdf.py
"""
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "CANZONIERE_DEFINITIVO.pdf"
ELENCO = ROOT / "ELENCO.txt"
SONGS = ROOT / "songs"

COL_SPLIT = 298
LINE_TOL = 4.5
# Keyed by normalized (uppercase) form to match normalize() output.
CATEGORY_HEADERS = {
    "CANZONI PER LA PREGHIERA": "preghiera",
    "CANZONI ITALIANE": "italiane",
    "CANZONI INTERNAZIONALI": "internazionali",
    "CANTI SCOUT": "scout",
}

# ---- Chord recognition (fallback to font) -----------------------------------
ROOT_RE = r"(?:DO|RE|MI|FA|SOL|LA|SI)"
ACC_RE = r"(?:#|b)?"
QUAL_RE = r"(?:maj7|maj|min|sus2|sus4|sus|dim|aug|add9|add|m|°|\+|7|6|9|11|13|4|2)*"
CHORD_RE = re.compile(f"^{ROOT_RE}{ACC_RE}{QUAL_RE}(?:/{ROOT_RE}{ACC_RE})?$")


def norm_chord(tok):
    return tok.replace("♯", "#").replace("♭", "b")


def is_chord(tok):
    t = norm_chord(tok).strip("()[].,:;")
    return len(t) >= 2 and bool(CHORD_RE.match(t))


def normalize(s):
    s = s.replace("’", "'").replace("‘", "'")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", " ", s.upper()).strip()


def slugify(s):
    s = s.replace("’", "'").replace("‘", "'")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def split_artist(title):
    m = re.split(r"\s*[–\-]\s*", title, maxsplit=1)
    if len(m) == 2 and m[1]:
        return m[0].strip(), m[1].strip()
    return title.strip(), ""


# ---- ELENCO ------------------------------------------------------------------
def parse_elenco():
    songs = []
    category = None
    buf = ""
    for raw in ELENCO.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.upper() == "ELENCO":
            continue
        if normalize(line) in CATEGORY_HEADERS:
            category = CATEGORY_HEADERS[normalize(line)]
            continue
        buf = (buf + " " + line).strip() if buf else line
        m = re.match(r"^(.*?)\s+(\d{1,3})$", buf)
        if m:
            title, artist = split_artist(m.group(1).strip())
            songs.append({"title": title, "artist": artist, "category": category,
                          "norm_full": normalize(m.group(1)), "norm_title": normalize(title)})
            buf = ""
    return songs


# ---- PDF loading with font info ---------------------------------------------
def page_spans(page):
    spans = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                spans.append((s["bbox"], s["font"], s["size"]))
    return spans


def font_of(word, spans):
    cx = (word[0] + word[2]) / 2
    cy = (word[1] + word[3]) / 2
    for (bbox, font, size) in spans:
        if bbox[0] - 0.5 <= cx <= bbox[2] + 0.5 and bbox[1] - 0.5 <= cy <= bbox[3] + 0.5:
            return font, size
    return "", 0


def group_lines(words):
    words = sorted(words, key=lambda w: (w["y0"], w["x0"]))
    lines, cur, cur_y = [], [], None
    for w in words:
        if cur_y is None or abs(w["y0"] - cur_y) <= LINE_TOL:
            cur.append(w)
            cur_y = w["y0"] if cur_y is None else cur_y
        else:
            lines.append(cur)
            cur, cur_y = [w], w["y0"]
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda w: w["x0"])
        n = len(ln)
        text = " ".join(w["text"] for w in ln)
        letters = [c for c in text if c.isalpha()]
        upper = sum(c.isupper() for c in letters) / len(letters) if letters else 0
        bold = sum(1 for w in ln if w["bold"])
        ital = sum(1 for w in ln if w["italic"])
        is_title = (bold / n >= 0.6 and ital / n < 0.3 and upper >= 0.7
                    and 0 < len(text) <= 60 and n <= 10 and normalize(text) not in CATEGORY_HEADERS)
        chord_frac = sum(1 for w in ln if is_chord(w["text"])) / n
        is_chord_line = (not is_title) and (ital / n >= 0.5 or chord_frac >= 0.6)
        out.append({
            "y": ln[0]["y0"], "text": text,
            "words": [(w["x0"], w["x1"], w["text"]) for w in ln],
            "is_title": is_title, "is_chord": is_chord_line,
        })
    return out


def load_pdf():
    doc = pymupdf.open(PDF)
    # The printed index at the end repeats "Canzoni per la preghiera"; stop there
    # so TOC entries aren't mistaken for songs.
    index_start = doc.page_count
    for pno in range(1, doc.page_count):
        if "CANZONI PER LA PREGHIERA" in normalize(doc[pno].get_text()):
            index_start = pno
            break
    print(f"Content pages: 1..{index_start}  (index starts at page {index_start + 1})")

    stream = []
    page_cat = []
    cur_cat = None
    for pno in range(index_start):
        page = doc[pno]
        spans = page_spans(page)
        # section header for this page (large text)
        for (bbox, font, size) in spans:
            pass
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if s["size"] >= 16 and normalize(s["text"]) in CATEGORY_HEADERS:
                        cur_cat = CATEGORY_HEADERS[normalize(s["text"])]
        page_cat.append(cur_cat)

        words = []
        for w in page.get_text("words"):
            font, size = font_of(w, spans)
            words.append({"x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3], "text": w[4],
                          "bold": ("Bold" in font), "italic": ("Italic" in font)})
        for col_words in ([w for w in words if w["x0"] < COL_SPLIT],
                          [w for w in words if w["x0"] >= COL_SPLIT]):
            for ln in group_lines(col_words):
                ln["page"] = pno
                ln["col"] = "L" if col_words and col_words[0]["x0"] < COL_SPLIT else "R"
                stream.append(ln)
    return stream, page_cat


# ---- Chord merging -----------------------------------------------------------
def merge_chords(chord_line, lyric_line):
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
        chord = norm_chord(ctxt).strip("()")
        idx = None
        for (x0, x1, cs, wl) in anchors:
            if abs(cx0 - x0) <= 3.5:
                idx = cs
                break
        if idx is None:
            if anchors and cx0 <= anchors[0][0]:
                idx = 0
            else:
                for (x0, x1, cs, wl) in anchors:
                    if x0 <= cx0 <= x1:
                        idx = cs + int((cx0 - x0) / max(1.0, (x1 - x0)) * wl)
                        break
                if idx is None:
                    after = [a for a in anchors if a[0] > cx0]
                    idx = after[0][2] if after else len(lyric)
        inserts.append((idx, f"[{chord}]"))

    inserts.sort(key=lambda t: t[0])
    out, last = [], 0
    for idx, tag in inserts:
        idx = max(0, min(len(lyric), idx))
        out.append(lyric[last:idx])
        out.append(tag)
        last = idx
    out.append(lyric[last:])
    return "".join(out)


def chords_only_line(line):
    return " ".join(f"[{norm_chord(w[2]).strip('()')}]" for w in line["words"])


# ---- Body assembly -----------------------------------------------------------
def build_body(lines):
    lines = [ln for ln in lines
             if not ln["is_title"]
             and not re.fullmatch(r"\d{1,3}", ln["text"].strip())
             and normalize(ln["text"]) not in CATEGORY_HEADERS]
    if not lines:
        return ""
    gaps = sorted(b["y"] - a["y"] for a, b in zip(lines, lines[1:])
                  if a["page"] == b["page"] and a["col"] == b["col"] and b["y"] > a["y"])
    med = gaps[len(gaps) // 2] if gaps else 13.0
    stanza_gap = med * 1.7

    out, i, prev, n = [], 0, None, len(lines)
    while i < n:
        line = lines[i]
        if prev is not None:
            same = prev["page"] == line["page"] and prev["col"] == line["col"]
            if same and line["y"] - prev["y"] > stanza_gap and out and out[-1] != "":
                out.append("")
            elif not same and out and out[-1] != "":
                out.append("")
        text = line["text"].strip()
        if re.match(r"^Rit\.?", text, re.I) or re.fullmatch(r"\[.*\]", text):
            out.append(f"{{comment: {text}}}")
            prev, i = line, i + 1
            continue
        if line["is_chord"]:
            nxt = lines[i + 1] if i + 1 < n else None
            if (nxt and not nxt["is_chord"] and not nxt["is_title"]
                    and not re.match(r"^Rit", nxt["text"], re.I)
                    and nxt["page"] == line["page"] and nxt["col"] == line["col"]
                    and (nxt["y"] - line["y"]) < stanza_gap):
                out.append(merge_chords(line, nxt))
                prev, i = nxt, i + 2
                continue
            out.append(chords_only_line(line))
            prev, i = line, i + 1
            continue
        out.append(text)
        prev, i = line, i + 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


# ---- Song boundaries ---------------------------------------------------------
def is_titleish(text):
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 2:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.7


def elenco_starts(stream, elenco):
    """Reliable path: match ELENCO titles against the text stream, in order.
    Returns (stream_index, elenco_index, title_line_count)."""
    starts, ei = [], 0
    for si, line in enumerate(stream):
        norm = normalize(line["text"])
        if not norm or norm in CATEGORY_HEADERS or line["is_chord"]:
            continue
        nxt = stream[si + 1] if si + 1 < len(stream) else None
        norm2 = normalize(line["text"] + " " + nxt["text"]) if nxt and not nxt["is_chord"] else None
        titleish = is_titleish(re.split(r"\s*[–-]\s*", line["text"], maxsplit=1)[0])
        for k in range(6):
            j = ei + k
            if j >= len(elenco):
                break
            full, title = elenco[j]["norm_full"], elenco[j]["norm_title"]
            span = 1
            m = norm == full or norm == title
            if not m and titleish and len(norm) >= 4:
                m = full.startswith(norm) or title.startswith(norm) or norm.startswith(title)
            if not m and norm2 and (norm2 == full or norm2 == title):
                m, span = True, 2  # title wrapped onto two lines
            if m:
                starts.append((si, j, span))
                ei = j + 1
                break
    return starts


def bold_extras(stream, after_si):
    """Songs missing from the (truncated) ELENCO: bold headings past the last
    catalogued song. Wrapped title lines are merged."""
    extras = []
    for si, line in enumerate(stream):
        if si <= after_si or not line["is_title"]:
            continue
        norm = normalize(line["text"])
        if not norm or norm in CATEGORY_HEADERS or re.fullmatch(r"\d{1,3}", line["text"].strip()):
            continue
        if extras and extras[-1][0] == si - 1:
            p = stream[si - 1]
            if p["is_title"] and p["page"] == line["page"] and p["col"] == line["col"]:
                extras[-1] = (extras[-1][0], extras[-1][1] + " " + line["text"])
                continue
        extras.append((si, line["text"]))
    return extras


# ---- Main --------------------------------------------------------------------
def main():
    elenco = parse_elenco()
    stream, page_cat = load_pdf()

    es = elenco_starts(stream, elenco)
    last_si = es[-1][0] if es else -1
    ex = bold_extras(stream, last_si)

    entries = []
    for si, ei, span in es:
        e = elenco[ei]
        entries.append((si, span, e["title"], e["artist"], e["category"]))
    for si, text in ex:
        title, artist = split_artist(text.strip())
        entries.append((si, 1, title, artist, page_cat[stream[si]["page"]] or "scout"))
    entries.sort(key=lambda x: x[0])
    idx = [e[0] for e in entries]

    SONGS.mkdir(exist_ok=True)
    for f in SONGS.glob("*.cho"):
        f.unlink()

    used = {}
    for n, (si, span, title, artist, cat) in enumerate(entries):
        end = idx[n + 1] if n + 1 < len(entries) else len(stream)
        body = build_body(stream[si + span:end])
        slug = slugify(title) or f"song-{si}"
        used[slug] = used.get(slug, 0) + 1
        if used[slug] > 1:
            slug = f"{slug}-{used[slug]}"
        head = [f"{{title: {title}}}"]
        if artist:
            head.append(f"{{subtitle: {artist}}}")
        head.append(f"{{categories: {cat}}}")
        (SONGS / f"{slug}.cho").write_text("\n".join(head) + "\n\n" + body + "\n", encoding="utf-8")

    matched = {ei for _, ei, _ in es}
    missing = [e["title"] for i, e in enumerate(elenco) if i not in matched]
    print(f"ELENCO matched: {len(es)}/{len(elenco)}")
    print(f"Extra scout-tail songs detected: {len(ex)}")
    print(f"Total written: {len(entries)}")
    if missing:
        print("Unmatched ELENCO titles:")
        for t in missing:
            print(f"  - {t}")
    print("Extra songs:")
    for _, text in ex:
        print(f"  + {text}")


if __name__ == "__main__":
    main()
