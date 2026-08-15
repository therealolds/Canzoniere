// ChordPro engine tuned for Italian solfège notation (DO RE MI FA SOL LA SI).
// Handles parsing, transposition and HTML rendering with zero dependencies.

// Chromatic scale, sharp spelling.
const SCALE = ['DO', 'DO#', 'RE', 'RE#', 'MI', 'FA', 'FA#', 'SOL', 'SOL#', 'LA', 'LA#', 'SI'];

// Flat spellings map onto their sharp index.
const FLAT_TO_INDEX = {
  DOb: 11, REb: 1, MIb: 3, FAb: 4, SOLb: 6, LAb: 8, SIb: 10,
};
const SHARP_TO_INDEX = {
  'DO#': 1, 'RE#': 3, 'MI#': 5, 'FA#': 6, 'SOL#': 8, 'LA#': 10, 'SI#': 0,
};
const NATURAL_TO_INDEX = { DO: 0, RE: 2, MI: 4, FA: 5, SOL: 7, LA: 9, SI: 11 };

// Match a root note (longest first so SOL/DO# win over SO/DO) at start of a token.
const ROOT_RE = /^(SOL|DO|RE|MI|FA|LA|SI)(#|b)?/;

function noteToIndex(note) {
  if (SHARP_TO_INDEX[note] !== undefined) return SHARP_TO_INDEX[note];
  if (FLAT_TO_INDEX[note] !== undefined) return FLAT_TO_INDEX[note];
  if (NATURAL_TO_INDEX[note] !== undefined) return NATURAL_TO_INDEX[note];
  return null;
}

// Transpose a single chord token (e.g. "DO#m7/SOL") by `steps` semitones.
// Unrecognised tokens are returned unchanged so lyrics/annotations survive.
export function transposeChord(chord, steps) {
  if (!steps) return chord;
  return chord.split('/').map((part) => {
    const m = part.match(ROOT_RE);
    if (!m) return part;
    const root = m[1] + (m[2] || '');
    const idx = noteToIndex(root);
    if (idx === null) return part;
    const newRoot = SCALE[(((idx + steps) % 12) + 12) % 12];
    return newRoot + part.slice(root.length);
  }).join('/');
}

// Is this bracketed token an actual chord (vs. an annotation like [x2] or [Rit.])?
function looksLikeChord(token) {
  return ROOT_RE.test(token) && !/\s/.test(token);
}

// Parse ChordPro source into { meta, blocks }.
// blocks: array of { type, ... }
//   type 'line'    -> { segments: [{chord, text}], chorus }
//   type 'comment' -> { text }
//   type 'break'   -> stanza separator
export function parseSong(source) {
  const meta = { title: '', subtitle: '', key: '', categories: [], tempo: null, explicit: false };
  const blocks = [];
  let inChorus = false;
  let pendingBreak = false;

  // Choruses are captured on first appearance so {chorus} can reprint them
  // (with chords) later — no manual duplication in the source file.
  const choruses = {};       // label -> array of segment-lists
  let currentChorus = null;  // { key, lines }
  let lastChorusKey = null;

  const flushBreak = () => {
    if (pendingBreak) { blocks.push({ type: 'break' }); pendingBreak = false; }
  };

  const lines = source.replace(/\r\n?/g, '\n').split('\n');

  for (const raw of lines) {
    const line = raw.replace(/\s+$/g, '');

    if (line.trim() === '') {
      pendingBreak = blocks.length > 0;
      continue;
    }

    // Directive: {name} or {name: value}
    const dir = line.match(/^\{\s*([^:}]+?)\s*(?::\s*(.*?)\s*)?\}$/);
    if (dir) {
      const name = dir[1].toLowerCase();
      const value = dir[2] || '';
      switch (name) {
        case 'title': case 't': meta.title = value; break;
        case 'subtitle': case 'st': meta.subtitle = value; break;
        case 'key': meta.key = value; break;
        case 'tempo': meta.tempo = parseInt(value, 10) || null; break;
        case 'explicit': meta.explicit = true; break;
        case 'categories': case 'category': case 'tags':
          meta.categories = value.split(',').map((s) => s.trim()).filter(Boolean);
          break;
        case 'start_of_chorus': case 'soc':
          inChorus = true;
          currentChorus = { key: value || '__default__', lines: [] };
          break;
        case 'end_of_chorus': case 'eoc':
          inChorus = false;
          if (currentChorus) {
            choruses[currentChorus.key] = currentChorus.lines;
            lastChorusKey = currentChorus.key;
            currentChorus = null;
          }
          break;
        case 'chorus': {
          // Reprint a previously defined chorus, with chords.
          const key = value || lastChorusKey || '__default__';
          const stored = choruses[key];
          flushBreak();
          if (stored && stored.length) {
            blocks.push({ type: 'chorus_label', text: 'Rit.' });
            for (const segs of stored) {
              blocks.push({ type: 'line', chorus: true, recalled: true, segments: segs });
            }
          } else {
            blocks.push({ type: 'comment', text: 'Rit.' });
          }
          break;
        }
        case 'comment': case 'c':
          flushBreak();
          blocks.push({ type: 'comment', text: value });
          break;
        default: break; // ignore unknown directives
      }
      continue;
    }

    flushBreak();
    const segments = parseLine(line);
    blocks.push({ type: 'line', chorus: inChorus, segments });
    if (inChorus && currentChorus) currentChorus.lines.push(segments);
  }

  return { meta, blocks };
}

// Split a lyric line into { chord, text } segments at each [chord] marker.
function parseLine(line) {
  const segments = [];
  const re = /\[([^\]]*)\]/g;
  let last = 0;
  let pendingChord = '';
  let m;
  while ((m = re.exec(line)) !== null) {
    const text = line.slice(last, m.index);
    if (text.length > 0 || pendingChord) {
      segments.push({ chord: pendingChord, text });
    }
    pendingChord = looksLikeChord(m[1]) ? m[1] : '';
    // Non-chord bracket content (annotations) is kept as visible text.
    if (!looksLikeChord(m[1]) && m[1]) {
      // reattach as text following segment
      segments.push({ chord: '', text: `[${m[1]}]` });
      pendingChord = '';
    }
    last = re.lastIndex;
  }
  const tail = line.slice(last);
  if (tail.length > 0 || pendingChord) {
    segments.push({ chord: pendingChord, text: tail });
  }
  if (segments.length === 0) segments.push({ chord: '', text: '' });
  return segments;
}

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// Render parsed song to HTML. options: { transpose:int, showChords:bool }
export function renderSong(parsed, options = {}) {
  const steps = options.transpose || 0;
  const html = [];
  for (const block of parsed.blocks) {
    if (block.type === 'break') { html.push('<div class="stanza-break"></div>'); continue; }
    if (block.type === 'comment') {
      html.push(`<div class="song-comment">${escapeHtml(block.text)}</div>`);
      continue;
    }
    if (block.type === 'chorus_label') {
      html.push(`<div class="chorus-label">${escapeHtml(block.text)}</div>`);
      continue;
    }
    let cls = block.chorus ? 'song-line chorus' : 'song-line';
    if (block.recalled) cls += ' recalled';
    const parts = block.segments.map((seg) => {
      const chord = seg.chord ? transposeChord(seg.chord, steps) : '';
      const chordHtml = chord ? `<span class="chord">${escapeHtml(chord)}</span>` : '<span class="chord"></span>';
      const text = escapeHtml(seg.text).replace(/ /g, '&nbsp;');
      return `<span class="seg"><span class="chord-slot">${chordHtml}</span><span class="lyric">${text || '&nbsp;'}</span></span>`;
    }).join('');
    html.push(`<div class="${cls}">${parts}</div>`);
  }
  return html.join('\n');
}

// Plain lyrics (chords + directives stripped) for search indexing.
export function plainLyrics(source) {
  return source
    .replace(/^\{.*\}$/gm, '')
    .replace(/\[[^\]]*\]/g, '')
    .replace(/\n{2,}/g, '\n')
    .trim();
}

// Render a parsed song to plain text for export.
// opts.chords=false -> lyrics only; true -> chords on a line above the lyrics.
export function songToText(parsed, opts = {}) {
  const withChords = !!opts.chords;
  const out = [];
  const title = parsed.meta.title || '';
  if (title) out.push(title.toUpperCase());
  if (parsed.meta.subtitle) out.push(`(${parsed.meta.subtitle})`);
  if (title || parsed.meta.subtitle) out.push('');

  for (const block of parsed.blocks) {
    if (block.type === 'break') { out.push(''); continue; }
    if (block.type === 'comment' || block.type === 'chorus_label') { out.push(block.text); continue; }
    if (block.type !== 'line') continue;

    if (withChords) {
      let lyric = '';
      let chordLine = '';
      let hasChord = false;
      for (const seg of block.segments) {
        if (seg.chord) {
          hasChord = true;
          if (chordLine.length < lyric.length) chordLine += ' '.repeat(lyric.length - chordLine.length);
          chordLine += seg.chord + ' ';
        }
        lyric += seg.text;
      }
      if (hasChord) out.push(chordLine.replace(/\s+$/, ''));
      out.push(lyric);
    } else {
      out.push(block.segments.map((s) => s.text).join(''));
    }
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}
