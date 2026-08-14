import { parseSong, renderSong, plainLyrics, songToText } from './chordpro.js';
import { mountTuner } from './tuner.js';

// ---- Category display config -------------------------------------------------
const CATEGORY_LABELS = {
  preghiera: 'Canzoni per la preghiera',
  italiane: 'Canzoni italiane',
  internazionali: 'Canzoni internazionali',
  scout: 'Canzoni scout',
};
const CATEGORY_ORDER = ['preghiera', 'italiane', 'internazionali', 'scout'];

function categoryLabel(cat) { return CATEGORY_LABELS[cat] || cat; }
function categoryRank(cat) {
  const i = CATEGORY_ORDER.indexOf(cat);
  return i === -1 ? CATEGORY_ORDER.length : i;
}

// ---- State -------------------------------------------------------------------
const state = {
  songs: [],
  bySlug: new Map(),
  showChords: loadPref('showChords', false),
};

const app = document.getElementById('app');
const searchInput = document.getElementById('search');
const menuBtn = document.getElementById('menu-btn');
const drawer = document.getElementById('drawer');
const backdrop = document.getElementById('drawer-backdrop');

// ---- Utils -------------------------------------------------------------------
// Accent- and case-insensitive normalisation for search (gesù -> gesu).
function normalize(s) {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

function loadPref(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : JSON.parse(v);
  } catch { return fallback; }
}
function savePref(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
}

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// ---- Theme -------------------------------------------------------------------
const darkQuery = matchMedia('(prefers-color-scheme: dark)');
function applyTheme(theme) {
  const dark = theme === 'dark' || (theme === 'auto' && darkQuery.matches);
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
}

// ---- Drawer menu -------------------------------------------------------------
function openMenu() {
  drawer.classList.add('open');
  backdrop.classList.add('open');
  menuBtn.setAttribute('aria-expanded', 'true');
}
function closeMenu() {
  drawer.classList.remove('open');
  backdrop.classList.remove('open');
  menuBtn.setAttribute('aria-expanded', 'false');
}

// ---- Data load ---------------------------------------------------------------
async function loadSongs() {
  const res = await fetch('./songs.json', { cache: 'no-cache' });
  if (!res.ok) throw new Error(`Impossibile caricare songs.json (${res.status})`);
  const raw = await res.json();
  state.songs = raw.map((s) => ({
    ...s,
    search: normalize(`${s.title} ${s.subtitle || ''} ${plainLyrics(s.body)}`),
  }));
  state.bySlug = new Map(state.songs.map((s) => [s.slug, s]));
}

// ---- Views -------------------------------------------------------------------
function renderHome(query = '') {
  const q = normalize(query.trim());
  const matches = q
    ? state.songs.filter((s) => s.search.includes(q))
    : state.songs;

  if (matches.length === 0) {
    app.innerHTML = `<p class="empty">Nessuna canzone trovata per “${escapeHtml(query)}”.</p>`;
    return;
  }

  // Group by (primary) category.
  const groups = new Map();
  for (const song of matches) {
    const cats = song.categories.length ? song.categories : ['(senza categoria)'];
    for (const cat of cats) {
      if (!groups.has(cat)) groups.set(cat, []);
      groups.get(cat).push(song);
    }
  }
  const sortedCats = [...groups.keys()].sort((a, b) => categoryRank(a) - categoryRank(b) || a.localeCompare(b));

  const searching = q.length > 0;
  const openCats = new Set(loadPref('openCats', []));

  const parts = [];
  if (q) parts.push(`<p class="result-count">${matches.length} risultat${matches.length === 1 ? 'o' : 'i'}</p>`);
  for (const cat of sortedCats) {
    const list = groups.get(cat).slice().sort((a, b) => a.title.localeCompare(b.title, 'it'));
    const open = searching || openCats.has(cat);
    parts.push(`<details class="category" data-cat="${escapeHtml(cat)}"${open ? ' open' : ''}>
      <summary class="category-title">
        <span class="chevron">▸</span>
        <span class="cat-name">${escapeHtml(categoryLabel(cat))}</span>
        <span class="count">${list.length}</span>
      </summary>
      <ul class="song-list">
        ${list.map((s) => `<li><a href="#/song/${encodeURIComponent(s.slug)}">
          <span class="song-title">${escapeHtml(s.title)}</span>
          ${s.subtitle ? `<span class="song-sub">${escapeHtml(s.subtitle)}</span>` : ''}
        </a></li>`).join('')}
      </ul>
    </details>`);
  }
  app.innerHTML = parts.join('\n');

  // Remember collapsed/expanded state per device (skip while searching).
  if (!searching) {
    app.querySelectorAll('details.category').forEach((d) => {
      d.addEventListener('toggle', () => {
        const set = new Set(loadPref('openCats', []));
        if (d.open) set.add(d.dataset.cat); else set.delete(d.dataset.cat);
        savePref('openCats', [...set]);
      });
    });
  }
}

function renderSongView(slug) {
  const song = state.bySlug.get(slug);
  if (!song) {
    app.innerHTML = `<p class="empty">Canzone non trovata. <a href="#/">Torna alle canzoni</a></p>`;
    return;
  }
  const parsed = parseSong(song.body);
  // Per-view transpose, reset on each open.
  let transpose = 0;

  function draw() {
    const keyLabel = parsed.meta.key
      ? `<span class="song-key">Tono: ${escapeHtml(parsed.meta.key)}${transpose ? ` (${transpose > 0 ? '+' : ''}${transpose})` : ''}</span>`
      : '';
    app.innerHTML = `
      <article class="song ${state.showChords ? '' : 'hide-chords'}">
        <div class="song-head">
          <a class="back" href="#/">‹ Canzoni</a>
          <h1 class="song-name">${escapeHtml(parsed.meta.title || song.title)}</h1>
          ${parsed.meta.subtitle ? `<p class="song-subtitle">${escapeHtml(parsed.meta.subtitle)}</p>` : ''}
        </div>
        <div class="song-controls">
          <button id="toggle-chords" class="ctl" aria-pressed="${state.showChords}">
            ${state.showChords ? 'Accordi: ON' : 'Accordi: OFF'}
          </button>
          <div class="transpose ${state.showChords ? '' : 'disabled'}">
            <button id="tr-down" class="ctl" title="Abbassa">−</button>
            ${keyLabel || '<span class="song-key">Trasporta</span>'}
            <button id="tr-up" class="ctl" title="Alza">+</button>
            <button id="tr-reset" class="ctl" title="Ripristina">↺</button>
          </div>
        </div>
        <div class="song-body">${renderSong(parsed, { transpose, showChords: state.showChords })}</div>
      </article>`;

    document.getElementById('toggle-chords').onclick = () => {
      state.showChords = !state.showChords;
      savePref('showChords', state.showChords);
      draw();
    };
    document.getElementById('tr-down').onclick = () => { transpose -= 1; draw(); };
    document.getElementById('tr-up').onclick = () => { transpose += 1; draw(); };
    document.getElementById('tr-reset').onclick = () => { transpose = 0; draw(); };
    window.scrollTo(0, 0);
  }
  draw();
}

// ---- Settings / static pages -------------------------------------------------
function renderSettings() {
  const current = loadPref('theme', 'auto');
  const opt = (val, label) => `<label class="radio">
    <input type="radio" name="theme" value="${val}"${current === val ? ' checked' : ''} />
    <span>${label}</span>
  </label>`;
  app.innerHTML = `<section class="page">
    <a class="back" href="#/">‹ Canzoni</a>
    <h1>Impostazioni</h1>
    <div class="setting">
      <h2>Tema</h2>
      <div class="radio-group">
        ${opt('light', 'Chiaro')}
        ${opt('dark', 'Scuro')}
        ${opt('auto', 'Automatico (sistema)')}
      </div>
    </div>
    <div class="setting">
      <h2>Accordi</h2>
      <label class="radio">
        <input type="checkbox" id="chords-pref"${state.showChords ? ' checked' : ''} />
        <span>Mostra accordi (per chi suona)</span>
      </label>
      <p class="hint">Impostazione salvata: le canzoni si apriranno con gli accordi ${state.showChords ? 'visibili' : 'nascosti'}.</p>
    </div>
  </section>`;
  app.querySelectorAll('input[name="theme"]').forEach((r) => {
    r.addEventListener('change', () => {
      savePref('theme', r.value);
      applyTheme(r.value);
    });
  });
  const chordsPref = document.getElementById('chords-pref');
  chordsPref.addEventListener('change', () => {
    state.showChords = chordsPref.checked;
    savePref('showChords', state.showChords);
    renderSettings(); // refresh the hint text
  });
  window.scrollTo(0, 0);
}

function renderInfo() {
  const repo = 'https://github.com/therealolds/Canzoniere';
  app.innerHTML = `<section class="page info">
    <a class="back" href="#/">‹ Canzoni</a>
    <h1>Info</h1>

    <p>Canzoniere del gruppo scout: testi e accordi, con ricerca, accordi
    attivabili/disattivabili, trasposizione per chi suona e accordatore.
    Funziona anche offline.</p>

    <h2>Codice sorgente</h2>
    <p>Il progetto è open source. Puoi vedere il codice, segnalare problemi
    o proporre nuovi canti qui:</p>
    <p><a href="${repo}" target="_blank" rel="noopener">github.com/therealolds/Canzoniere ↗</a></p>

    <h2>Privacy e cookie</h2>
    <ul>
      <li><strong>Nessun cookie</strong> e nessun tracciamento pubblicitario.</li>
      <li>Le tue <strong>preferenze</strong> (tema, accordi on/off, categorie aperte/chiuse)
      sono salvate solo sul tuo dispositivo (<em>localStorage</em>) e non vengono inviate a nessuno.</li>
      <li>L'<strong>accordatore</strong> usa il microfono solo sul momento, dentro il browser:
      l'audio non viene registrato né inviato da nessuna parte.</li>
      <li>Il sito è ospitato su <strong>GitHub Pages</strong>, che può conservare log di accesso
      tecnici standard (come qualsiasi sito web).</li>
    </ul>

    <h2>Uso offline</h2>
    <p>Puoi installare il Canzoniere sul telefono (dal menu del browser,
    “Aggiungi a schermata Home”) e usarlo <strong>senza connessione</strong>,
    utile ai campi e nei bivacchi.</p>

    <h2>Aggiungere o correggere un canto</h2>
    <p>Ogni canto è un file di testo in formato ChordPro nella cartella
    <code>songs/</code>. Le istruzioni complete sono nel
    <a href="${repo}#readme" target="_blank" rel="noopener">README</a>.</p>

    <p class="hint">Per il gruppo scout · in cammino.</p>
  </section>`;
  window.scrollTo(0, 0);
}

function renderUtilities() {
  app.innerHTML = `<section class="page">
    <a class="back" href="#/">‹ Canzoni</a>
    <h1>Strumenti</h1>
    <div class="tool-list">
      <a class="tool-card" href="#/tuner">
        <span class="tool-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h3l2.5-7 4 14 2.5-7H21" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
        <span class="tool-text"><strong>Accordatore</strong>
        <small>Accorda la chitarra col microfono o con le note di riferimento.</small></span>
      </a>
      <a class="tool-card" href="#/export">
        <span class="tool-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 13h6M9 17h4" stroke-linecap="round"/></svg></span>
        <span class="tool-text"><strong>Esporta canzoni</strong>
        <small>Seleziona dei canti ed esporta i testi, con o senza accordi.</small></span>
      </a>
    </div>
  </section>`;
  window.scrollTo(0, 0);
}

function renderTuner() {
  pageCleanup = mountTuner(app);
  window.scrollTo(0, 0);
}

function renderExport() {
  const selected = new Set();
  let withChords = false;
  let filter = '';

  app.innerHTML = `<section class="page export">
    <a class="back" href="#/utilities">‹ Strumenti</a>
    <h1>Esporta canzoni</h1>

    <input id="ex-search" class="ex-search" type="search" placeholder="Cerca per titolo o testo…" autocomplete="off" />
    <div class="ex-toolbar">
      <span id="ex-count" class="ex-count">0 selezionate</span>
      <button id="ex-clear" class="ctl small">Deseleziona</button>
      <label class="ex-chords"><input type="checkbox" id="ex-chords" /> Con accordi</label>
    </div>

    <div id="ex-list" class="ex-list"></div>

    <h2 class="tuner-sub">Anteprima</h2>
    <textarea id="ex-out" class="ex-out" readonly placeholder="Seleziona uno o più canti…"></textarea>
    <div class="ex-actions">
      <button id="ex-copy" class="ctl">Copia</button>
      <button id="ex-download" class="ctl">Scarica .txt</button>
      <span id="ex-status" class="hint"></span>
    </div>
  </section>`;

  const searchEl = app.querySelector('#ex-search');
  const listEl = app.querySelector('#ex-list');
  const countEl = app.querySelector('#ex-count');
  const outEl = app.querySelector('#ex-out');
  const statusEl = app.querySelector('#ex-status');

  function buildOutput() {
    const chosen = state.songs
      .filter((s) => selected.has(s.slug))
      .sort((a, b) => a.title.localeCompare(b.title, 'it'));
    return chosen.map((s) => songToText(parseSong(s.body), { chords: withChords })).join('\n\n\n');
  }

  function updateOutput() {
    outEl.value = buildOutput();
    countEl.textContent = `${selected.size} selezionat${selected.size === 1 ? 'a' : 'e'}`;
    statusEl.textContent = '';
  }

  function renderList() {
    const q = normalize(filter.trim());
    const list = state.songs
      .filter((s) => !q || s.search.includes(q))
      .sort((a, b) => a.title.localeCompare(b.title, 'it'));
    if (list.length === 0) {
      listEl.innerHTML = `<p class="empty">Nessun canto trovato.</p>`;
      return;
    }
    listEl.innerHTML = list.map((s) => `<label class="ex-item">
      <input type="checkbox" data-slug="${escapeHtml(s.slug)}"${selected.has(s.slug) ? ' checked' : ''} />
      <span class="song-title">${escapeHtml(s.title)}</span>
      ${s.subtitle ? `<span class="song-sub">${escapeHtml(s.subtitle)}</span>` : ''}
    </label>`).join('');
    listEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener('change', () => {
        if (cb.checked) selected.add(cb.dataset.slug); else selected.delete(cb.dataset.slug);
        updateOutput();
      });
    });
  }

  searchEl.addEventListener('input', () => { filter = searchEl.value; renderList(); });
  app.querySelector('#ex-chords').addEventListener('change', (e) => {
    withChords = e.target.checked;
    updateOutput();
  });
  app.querySelector('#ex-clear').addEventListener('click', () => {
    selected.clear();
    renderList();
    updateOutput();
  });
  app.querySelector('#ex-copy').addEventListener('click', async () => {
    if (!outEl.value) { statusEl.textContent = 'Niente da copiare.'; return; }
    try {
      await navigator.clipboard.writeText(outEl.value);
      statusEl.textContent = 'Copiato negli appunti ✓';
    } catch {
      outEl.select();
      document.execCommand('copy');
      statusEl.textContent = 'Copiato ✓';
    }
  });
  app.querySelector('#ex-download').addEventListener('click', () => {
    if (!outEl.value) { statusEl.textContent = 'Niente da scaricare.'; return; }
    const blob = new Blob([outEl.value], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = selected.size === 1 ? `${[...selected][0]}.txt` : 'canzoni.txt';
    a.click();
    URL.revokeObjectURL(url);
    statusEl.textContent = 'File scaricato ✓';
  });

  renderList();
  updateOutput();
  window.scrollTo(0, 0);
}

// ---- Router ------------------------------------------------------------------
// Some pages (e.g. the tuner) hold resources (mic, audio) that must be released
// when navigating away.
let pageCleanup = null;

function router() {
  if (pageCleanup) { pageCleanup(); pageCleanup = null; }

  const hash = location.hash || '#/';
  const songMatch = hash.match(/^#\/song\/(.+)$/);
  if (songMatch) renderSongView(decodeURIComponent(songMatch[1]));
  else if (hash === '#/settings') renderSettings();
  else if (hash === '#/utilities') renderUtilities();
  else if (hash === '#/tuner') renderTuner();
  else if (hash === '#/export') renderExport();
  else if (hash === '#/info') renderInfo();
  else renderHome(searchInput.value);
}

// ---- Init --------------------------------------------------------------------
async function init() {
  try {
    await loadSongs();
  } catch (err) {
    app.innerHTML = `<p class="empty">${escapeHtml(err.message)}<br>
      Hai eseguito <code>python scripts/build_index.py</code>?</p>`;
    return;
  }

  const clearBtn = document.getElementById('search-clear');
  const onSearchChange = () => {
    clearBtn.hidden = searchInput.value === '';
    if (location.hash && location.hash !== '#/') location.hash = '#/';
    else renderHome(searchInput.value);
  };
  searchInput.addEventListener('input', onSearchChange);
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && searchInput.value) {
      e.stopPropagation();
      searchInput.value = '';
      onSearchChange();
    }
  });
  clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    searchInput.focus();
    onSearchChange();
  });

  // Hamburger menu
  menuBtn.addEventListener('click', () => {
    if (drawer.classList.contains('open')) closeMenu(); else openMenu();
  });
  backdrop.addEventListener('click', closeMenu);
  drawer.querySelectorAll('a[data-nav]').forEach((a) => a.addEventListener('click', closeMenu));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMenu(); });

  // Keep "automatic" theme in sync when the OS switches light/dark.
  darkQuery.addEventListener('change', () => {
    if (loadPref('theme', 'auto') === 'auto') applyTheme('auto');
  });

  window.addEventListener('hashchange', router);
  router();

  // Register the service worker for offline use (ignored on file://).
  if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
    navigator.serviceWorker.register('./sw.js').catch(() => { /* offline optional */ });
  }
}

init();
