#!/usr/bin/env python3
"""Add the songs pasted into tbd.txt to the songbook.

Each song in tbd.txt starts with a header line

    === Title | Artist | category

followed by the lyrics with the chords on the line ABOVE, as copied from chord
sites (accordiespartiti, Ultimate Guitar...). Italian (Do, La-, Sol7) and
English (C, Am, G7) chord names both work and are written in the site's
notation (DO, LAm, SOL7). Text already in ChordPro ([DO]words) is kept as is.
A song without the header line gets its title/artist/category asked for.

Every song becomes songs/<slug>.cho (an existing song is never overwritten
unless --force), is removed from tbd.txt, and songs.json is rebuilt.

    py scripts/add_songs.py               # process tbd.txt
    py scripts/add_songs.py --dry-run     # print the .cho files, write nothing
    py scripts/add_songs.py other.txt     # read another file
    py scripts/add_songs.py --force       # overwrite songs that already exist

Standard library only.
"""
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_index  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SONGS = ROOT / "songs"
INBOX = ROOT / "tbd.txt"
CATEGORIES = ("preghiera", "italiane", "internazionali", "scout")

TEMPLATE = """\
# Incolla qui sotto le canzoni da aggiungere, poi lancia:
#     py scripts/add_songs.py            (su Linux: python3 scripts/add_songs.py)
#     py scripts/add_songs.py --dry-run  (solo anteprima, non scrive niente)
#
# Ogni canzone inizia con una riga così (l'autore si può lasciare vuoto):
#     === Titolo | Autore | categoria
# categoria: preghiera, italiane, internazionali o scout (più di una: separate da virgola)
# Sotto, il testo con gli accordi SOPRA le parole, come lo copi dai siti di accordi.
# Le righe che iniziano con # vengono ignorate.
"""

# ---- Chords -------------------------------------------------------------------
IT_NOTE = r"(?:DO|Do|RE|Re|MI|Mi|FA|Fa|SOL|Sol|LA|La|SI|Si)[#b]?"
EN_NOTE = r"[A-G][#b]?"
SUFFIX = r"(?:maj|min|dim|aug|sus|add|m|M|\d|\+|-|°|[#b]\d|\([#b]?\d+\))*"
CHORD_RE = re.compile(rf"^({IT_NOTE}|{EN_NOTE})({SUFFIX})(?:/({IT_NOTE}|{EN_NOTE}|\d+))?$")
EN_TO_IT = {"C": "DO", "D": "RE", "E": "MI", "F": "FA", "G": "SOL", "A": "LA", "B": "SI"}
# Tokens that may sit on a chord line without being chords: bars, repeats, dots.
FILLER_RE = re.compile(r"^(?:\|+|/|-+|x\s?\d+|\(x\s?\d+\)|\.{2,}|…|%|:|\(|\))$", re.I)


def site_note(note):
    acc = note[-1] if len(note) > 1 and note[-1] in "#b" else ""
    base = note[:len(note) - len(acc)]
    return EN_TO_IT.get(base, base.upper()) + acc


def as_chord(tok):
    """'La-' -> 'LAm', 'Bb7' -> 'SIb7', 'Re/Fa#' -> 'RE/FA#'; None if not a chord."""
    t = tok.replace("♯", "#").replace("♭", "b")
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1]
    m = CHORD_RE.match(t)
    if not m:
        return None
    root, suffix, bass = m.groups()
    out = site_note(root) + re.sub(r"^(?:min|-)", "m", suffix)
    if bass:
        out += "/" + (bass if bass.isdigit() else site_note(bass))
    return out


def chord_line(line):
    """[(col, chord or None, token)] if every token is a chord or a filler, else None."""
    toks = [(m.start(), m.group()) for m in re.finditer(r"\S+", line)]
    out = [(col, as_chord(tok), tok) for col, tok in toks]
    if not any(c for _, c, _ in out):
        return None
    if any(c is None and not FILLER_RE.match(tok) for _, c, tok in out):
        return None
    return out


def merge(chords, lyric):
    """Drop each chord into the lyric at its column. A chord over a space moves
    onto the next word, unless another chord is waiting there."""
    chords = [(col, c) for col, c, _ in chords if c]
    places = []
    for k, (col, chord) in enumerate(chords):
        pos = min(col, len(lyric))
        if pos < len(lyric) and lyric[pos] == " ":
            nxt = pos
            while nxt < len(lyric) and lyric[nxt] == " ":
                nxt += 1
            if k + 1 == len(chords) or chords[k + 1][0] > nxt:
                pos = nxt
        places.append((pos, chord))
    out, last = [], 0
    for pos, chord in places:
        out += [lyric[last:pos], f"[{chord}]"]
        last = pos
    out.append(lyric[last:])
    return re.sub(r"\]\s+\[", "] [", "".join(out).strip())


def chords_only(chords):
    return " ".join(f"[{c}]" if c else tok for _, c, tok in chords)


# ---- Section labels -------------------------------------------------------------
RIT = "Rit."
# label word -> comment to print (None: drop it, e.g. every [Verse] on Ultimate Guitar)
LABELS = {
    "intro": "Intro", "strofa": None, "verse": None, "verso": None,
    "ritornello": RIT, "rit": RIT, "chorus": RIT, "refrain": RIT,
    "pre-rit": "Pre-rit.", "pre-chorus": "Pre-rit.", "prechorus": "Pre-rit.",
    "bridge": "Bridge", "ponte": "Bridge", "special": "Special",
    "solo": "Solo", "assolo": "Solo", "strumentale": "Strumentale", "instrumental": "Strumentale",
    "interludio": "Interludio", "interlude": "Interludio",
    "finale": "Finale", "outro": "Finale", "coda": "Coda", "fine": "Fine",
}
LABEL_RE = re.compile(
    r"^\s*(?P<open>[\[(])?\s*(?P<word>" + "|".join(sorted(map(re.escape, LABELS), key=len, reverse=True))
    + r")\b(?P<dot>\.)?\s*\d*\s*(?P<rep>x\s*\d+|\(x\s*\d+\))?\s*(?P<close>[\])])?\s*(?P<colon>:)?\s*",
    re.I,
)
PAGE_RE = re.compile(r"^\s*(?:page|pagina|pag\.?)\s*\d+\s*(?:/|di|of)\s*\d+\s*$", re.I)


def label(line):
    """(comment, is_rit, bracketed, rest_col) if the line opens with a section label."""
    m = LABEL_RE.match(line)
    if not m:
        return None
    rest = line[m.end():]
    word = m.group("word").lower()
    bracketed = bool(m.group("open") and m.group("close"))
    is_rit = LABELS[word] == RIT
    if not (bracketed or m.group("colon") or not rest.strip() or chord_line(rest)
            or (is_rit and m.group("dot"))):
        return None  # a lyric that starts with "Solo", "Fine"...
    text = LABELS[word]
    if text and m.group("rep"):
        text += " " + re.sub(r"\s", "", m.group("rep"))
    return text, is_rit, bracketed, m.end()


# ---- Body conversion --------------------------------------------------------------
def clean_lines(text):
    """Text lines without page markers (and the blank lines around them)."""
    out, skip_blank = [], False
    for raw in text.expandtabs(8).split("\n"):
        line = raw.rstrip()
        if PAGE_RE.match(line):
            while out and not out[-1].strip():
                out.pop()
            skip_blank = True
            continue
        if skip_blank and not line.strip():
            continue
        skip_blank = False
        out.append(line)
    return out


def items(lines):
    """Lines -> ("blank",) | ("label", comment, is_rit, bracketed) | ("line", chordpro)."""
    lines = list(lines)
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            out.append(("blank",))
            i += 1
            continue
        lab = label(line)
        if lab:
            out.append(("label",) + lab[:3])
            if not line[lab[3]:].strip():
                i += 1
                continue
            lines[i] = " " * lab[3] + line[lab[3]:]  # keep columns for the chords above
            line = lines[i]
        chords = chord_line(line)
        if not chords:
            out.append(("line", line.strip()))
            i += 1
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        lab = label(nxt) if nxt.strip() else None
        if lab and nxt[lab[3]:].strip() and not chord_line(nxt[lab[3]:]):
            out.append(("label",) + lab[:3])  # "Rit. Lyrics..." under a chord line
            nxt = lines[i + 1] = " " * lab[3] + nxt[lab[3]:]
        elif lab:
            nxt = ""
        if nxt.strip() and not chord_line(nxt):
            out.append(("line", merge(chords, nxt)))
            i += 2
        else:
            out.append(("line", chords_only(chords)))
            i += 1
    return out


def plain(stanza):
    text = " ".join(it[1] for it in stanza if it[0] == "line")
    text = re.sub(r"\[[^\]]*\]", "", text).lower()
    return " ".join(re.findall(r"\w+", text))


def convert(text):
    """Chords-above-lyrics text -> ChordPro body, with the chorus marked once."""
    stanzas, cur = [], []
    for it in items(clean_lines(text)):
        if it[0] == "blank":
            if cur:
                stanzas.append(cur)
            cur = []
        else:
            cur.append(it)
    if cur:
        stanzas.append(cur)

    blocks, chorus, k = [], None, 0
    while k < len(stanzas):
        s = stanzas[k]
        k += 1
        # A lone label heading the next stanza ("[Chorus]", blank, lyrics). A bare
        # "Rit." between stanzas is a repeat, unless no chorus has been written yet.
        if len(s) == 1 and s[0][0] == "label" and k < len(stanzas) and stanzas[k][0][0] != "label":
            _, _, is_rit, bracketed = s[0]
            nxt = stanzas[k]
            if bracketed or not is_rit or chorus is None or plain(nxt) == chorus:
                s = s + nxt
                k += 1
        body = [it for it in s[1:]] if s[0][0] == "label" and s[0][2] else None
        if body and any(it[0] == "line" for it in body):
            if chorus is not None and plain(body) == chorus:
                blocks.append(f"{{comment: {s[0][1]}}}")
                continue
            if chorus is None:
                chorus = plain(body)
            s = [("raw", "{start_of_chorus}")] + body + [("raw", "{end_of_chorus}")]
        out = []
        for it in s:
            if it[0] == "label":
                if it[1]:
                    out.append(f"{{comment: {it[1]}}}")
            else:
                out.append(it[1])
        if out:
            blocks.append("\n".join(out))
    return "\n\n".join(blocks)


def convert_chordpro(text):
    """Already ChordPro: keep it, only writing the chords in the site's notation."""
    lines = []
    for line in text.strip().split("\n"):
        m = build_index.DIRECTIVE_RE.match(line.strip())
        if m and m.group(1).lower() in ("title", "t", "subtitle", "st", "categories", "category", "tags"):
            continue
        lines.append(re.sub(r"\[([^\]]+)\]", lambda m: f"[{as_chord(m.group(1)) or m.group(1)}]", line.rstrip()))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def is_chordpro(text):
    return any(as_chord(t) for t in re.findall(r"\[([^\]\s]+)\]", text))


# ---- Inbox -------------------------------------------------------------------------
def slugify(s):
    s = s.replace("’", "'").replace("‘", "'")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def read_inbox(path):
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")  # Notepad's old "ANSI"


def split_blocks(text):
    """[(header line or None, body lines)]; '#' lines are dropped."""
    blocks, header, body = [], None, []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith("#"):
            continue
        if line.startswith("==="):
            if header is not None or any(l.strip() for l in body):
                blocks.append((header, body))
            header, body = line, []
        else:
            body.append(line)
    if header is not None or any(l.strip() for l in body):
        blocks.append((header, body))
    return blocks


def parse_categories(value):
    cats = [c.strip().lower() for c in value.split(",") if c.strip()]
    bad = [c for c in cats if c not in CATEGORIES]
    return cats, bad


def parse_header(header):
    """(title, artist, categories) or raise ValueError."""
    parts = [p.strip() for p in header.lstrip("=").split("|")]
    title = parts[0]
    artist, cats = "", ""
    if len(parts) == 2 and not parse_categories(parts[1])[1]:
        cats = parts[1]
    elif len(parts) >= 2:
        artist = parts[1]
        cats = parts[2] if len(parts) > 2 else ""
    if not title:
        raise ValueError("manca il titolo nella riga ===")
    cats, bad = parse_categories(cats)
    if not cats:
        raise ValueError(f"manca la categoria ({', '.join(CATEGORIES)})")
    if bad:
        raise ValueError(f"categoria sconosciuta: {', '.join(bad)} (valide: {', '.join(CATEGORIES)})")
    return title, artist, cats


def ask_header(body):
    """Ask for the header of a song pasted without one; None to skip it."""
    if not sys.stdin.isatty():
        return None
    first = next((l.strip() for l in body if l.strip() and not chord_line(l) and not label(l)), "")
    print(f"\nCanzone senza riga === : «{first[:60]}»")
    title = input("  Titolo (invio per saltarla): ").strip()
    if not title:
        return None
    artist = input("  Autore (invio per nessuno): ").strip()
    while True:
        cats, bad = parse_categories(input(f"  Categoria ({', '.join(CATEGORIES)}): "))
        if cats and not bad:
            return title, artist, cats
        print("  categoria non valida")


def make_song(title, artist, cats, body_text):
    body = convert_chordpro(body_text) if is_chordpro(body_text) else convert(body_text)
    head = [f"{{title: {title.upper()}}}"]
    if artist:
        head.append(f"{{subtitle: {artist}}}")
    head.append(f"{{categories: {', '.join(cats)}}}")
    return "\n".join(head) + "\n\n" + body + "\n"


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    force = "--force" in args
    files = [a for a in args if not a.startswith("--")]
    inbox = Path(files[0]) if files else INBOX
    if not inbox.exists():
        inbox.write_text(TEMPLATE, encoding="utf-8")
        print(f"Creato {inbox}: incollaci le canzoni e rilancia.")
        return

    added, left = [], []
    for header, body in split_blocks(read_inbox(inbox)):
        body_text = "\n".join(body)
        raw = "\n".join(([header] if header else []) + body).strip("\n")
        if not body_text.strip():
            continue
        try:
            meta = parse_header(header) if header else ask_header(body)
            if not meta:
                raise ValueError("manca la riga  === Titolo | Autore | categoria")
        except ValueError as e:
            print(f"!!! {(header or body_text.strip().splitlines()[0])[:60]}: {e}")
            left.append(raw)
            continue
        title, artist, cats = meta
        slug = slugify(title)
        dest = SONGS / f"{slug}.cho"
        if dest.exists() and not force:
            print(f"!!! {title}: esiste già songs/{dest.name} (usa --force per sostituirla)")
            left.append(raw)
            continue
        song = make_song(title, artist, cats, body_text)
        if dry:
            print(f"----- songs/{dest.name} -----\n{song}")
        else:
            dest.write_text(song, encoding="utf-8")
            print(f"+ songs/{dest.name}  ({title.upper()})")
        added.append(dest)

    if dry:
        print("(--dry-run: non ho scritto niente)")
        return
    inbox.write_text(TEMPLATE + "".join(f"\n{b}\n" for b in left), encoding="utf-8")
    if left:
        print(f"{len(left)} canzone/i lasciate in {inbox.name}: correggi e rilancia.")
    if added:
        build_index.main()
        print("Controlla le canzoni sul sito, poi commit + push.")
    elif not left:
        print(f"Nessuna canzone in {inbox.name}.")


if __name__ == "__main__":
    main()
