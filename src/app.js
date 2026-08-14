import { parseSong, renderSong, plainLyrics } from './chordpro.js';
import { mountTuner } from './tuner.js';

// ---- Category display config -------------------------------------------------
const CATEGORY_LABELS = {
  preghiera: 'Canzoni per la preghiera',
  italiane: 'Canzoni italiane',
  internazionali: 'Canzoni internazionali',
  scout: 'Canti scout',
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
  const collapsed = new Set(loadPref('collapsedCats', []));

  const parts = [];
  if (q) parts.push(`<p class="result-count">${matches.length} risultat${matches.length === 1 ? 'o' : 'i'}</p>`);
  for (const cat of sortedCats) {
    const list = groups.get(cat).slice().sort((a, b) => a.title.localeCompare(b.title, 'it'));
    const open = searching || !collapsed.has(cat);
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
        const set = new Set(loadPref('collapsedCats', []));
        if (d.open) set.delete(d.dataset.cat); else set.add(d.dataset.cat);
        savePref('collapsedCats', [...set]);
      });
    });
  }
}

function renderSongView(slug) {
  const song = state.bySlug.get(slug);
  if (!song) {
    app.innerHTML = `<p class="empty">Canzone non trovata. <a href="#/">Torna all'indice</a></p>`;
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
          <a class="back" href="#/">‹ Indice</a>
          <h1 class="song-name">${escapeHtml(parsed.meta.title || song.title)}</h1>
          ${parsed.meta.subtitle ? `<p class="song-subtitle">${escapeHtml(parsed.meta.subtitle)}</p>` : ''}
        </div>
        <div class="song-controls">
          <button id="toggle-chords" class="ctl" aria-pressed="${state.showChords}">
            ${state.showChords ? '🎸 Accordi: ON' : '🎤 Accordi: OFF'}
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
    <a class="back" href="#/">‹ Indice</a>
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

function renderPlaceholder(title) {
  app.innerHTML = `<section class="page">
    <a class="back" href="#/">‹ Indice</a>
    <h1>${escapeHtml(title)}</h1>
    <p class="empty">In arrivo.</p>
  </section>`;
  window.scrollTo(0, 0);
}

function renderUtilities() {
  pageCleanup = mountTuner(app);
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
  else if (hash === '#/info') renderPlaceholder('Info');
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

  searchInput.addEventListener('input', () => {
    if (location.hash && location.hash !== '#/') location.hash = '#/';
    else renderHome(searchInput.value);
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
