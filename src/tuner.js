// Guitar tuner for the "Strumenti" page. Zero dependencies:
// - microphone pitch detection via Web Audio autocorrelation
// - reference tones via an oscillator (no mic needed)
// mountTuner(container) renders the UI and returns a cleanup function.

const NOTE_NAMES = ['DO', 'DO#', 'RE', 'RE#', 'MI', 'FA', 'FA#', 'SOL', 'SOL#', 'LA', 'LA#', 'SI'];

// Standard tuning, low to high: E2 A2 D3 G3 B3 E4.
const STRINGS = [
  { name: 'MI', midi: 40, sub: 'E2' },
  { name: 'LA', midi: 45, sub: 'A2' },
  { name: 'RE', midi: 50, sub: 'D3' },
  { name: 'SOL', midi: 55, sub: 'G3' },
  { name: 'SI', midi: 59, sub: 'B3' },
  { name: 'MI', midi: 64, sub: 'E4' },
];

const midiToFreq = (m) => 440 * Math.pow(2, (m - 69) / 12);
const freqToMidi = (f) => 12 * (Math.log(f / 440) / Math.log(2)) + 69;

// Autocorrelation pitch detector (after Chris Wilson's PitchDetect).
// Returns frequency in Hz, or -1 when the signal is too quiet/unclear.
function autoCorrelate(buf, sampleRate) {
  let SIZE = buf.length;
  let rms = 0;
  for (let i = 0; i < SIZE; i++) rms += buf[i] * buf[i];
  rms = Math.sqrt(rms / SIZE);
  if (rms < 0.01) return -1; // too quiet

  let r1 = 0;
  let r2 = SIZE - 1;
  const thres = 0.2;
  for (let i = 0; i < SIZE / 2; i++) { if (Math.abs(buf[i]) < thres) { r1 = i; break; } }
  for (let i = 1; i < SIZE / 2; i++) { if (Math.abs(buf[SIZE - i]) < thres) { r2 = SIZE - i; break; } }

  const b = buf.slice(r1, r2);
  SIZE = b.length;
  // Only correlate lags down to a ~60 Hz floor — well below the lowest guitar
  // string (E2 ≈ 82 Hz) — which bounds the otherwise O(n²) cost.
  const maxLag = Math.min(SIZE - 1, Math.ceil(sampleRate / 60));
  const c = new Array(maxLag + 1).fill(0);
  for (let i = 0; i <= maxLag; i++) {
    for (let j = 0; j < SIZE - i; j++) c[i] += b[j] * b[j + i];
  }

  let d = 0;
  while (d < maxLag && c[d] > c[d + 1]) d++;
  let maxval = -1;
  let maxpos = -1;
  for (let i = d; i <= maxLag; i++) {
    if (c[i] > maxval) { maxval = c[i]; maxpos = i; }
  }
  let T0 = maxpos;
  if (T0 <= 0) return -1;

  // Parabolic interpolation for a finer peak.
  const x1 = c[T0 - 1] || 0;
  const x2 = c[T0];
  const x3 = c[T0 + 1] || 0;
  const a = (x1 + x3 - 2 * x2) / 2;
  const bb = (x3 - x1) / 2;
  if (a) T0 -= bb / (2 * a);

  return sampleRate / T0;
}

export function mountTuner(container) {
  container.innerHTML = `
    <section class="page tuner">
      <a class="back" href="#/utilities">‹ Strumenti</a>
      <h1>Accordatore</h1>

      <div class="tuner-display" id="t-display">
        <div class="tuner-note" id="t-note">–</div>
        <div class="tuner-meter">
          <div class="tuner-center"></div>
          <div class="tuner-needle" id="t-needle"></div>
        </div>
        <div class="tuner-cents" id="t-cents">±0</div>
      </div>

      <button id="t-start" class="ctl primary">Avvia microfono</button>
      <p class="hint" id="t-status">Serve il permesso del microfono (funziona solo su https o localhost).</p>

      <h2 class="tuner-sub">Note di riferimento</h2>
      <div class="tuner-strings" id="t-strings"></div>
      <p class="hint">Tocca una corda per sentirne il suono e accordare a orecchio.</p>
    </section>`;

  const noteEl = container.querySelector('#t-note');
  const needleEl = container.querySelector('#t-needle');
  const centsEl = container.querySelector('#t-cents');
  const displayEl = container.querySelector('#t-display');
  const startBtn = container.querySelector('#t-start');
  const statusEl = container.querySelector('#t-status');
  const stringsEl = container.querySelector('#t-strings');

  // ---- Shared audio context (created on first user gesture) ----
  let audioCtx = null;
  const getCtx = () => {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
    return audioCtx;
  };

  // ---- Reference tones ----
  const stringButtons = STRINGS.map((s, i) => {
    const btn = document.createElement('button');
    btn.className = 'ctl string-btn';
    btn.innerHTML = `<strong>${s.name}</strong><small>${s.sub}</small>`;
    btn.addEventListener('click', () => playTone(midiToFreq(s.midi)));
    btn.dataset.midi = String(s.midi);
    stringsEl.appendChild(btn);
    return btn;
  });

  function playTone(freq) {
    const ctx = getCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    const now = ctx.currentTime;
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.25, now + 0.02);
    gain.gain.setValueAtTime(0.25, now + 1.2);
    gain.gain.linearRampToValueAtTime(0, now + 1.6);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 1.65);
  }

  // ---- Microphone tuner ----
  let stream = null;
  let analyser = null;
  let rafId = null;
  let buffer = null;
  let listening = false;

  async function startMic() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      statusEl.textContent = 'Microfono non disponibile su questo dispositivo/contesto.';
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      statusEl.textContent = 'Permesso microfono negato. Il tuner non può ascoltare.';
      return;
    }
    const ctx = getCtx();
    const source = ctx.createMediaStreamSource(stream);
    analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    buffer = new Float32Array(analyser.fftSize);
    source.connect(analyser);
    listening = true;
    startBtn.textContent = 'Ferma';
    statusEl.textContent = 'In ascolto… suona una corda alla volta.';
    update();
  }

  function stopMic() {
    listening = false;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    analyser = null;
    startBtn.textContent = 'Avvia microfono';
    statusEl.textContent = 'Microfono fermo.';
    noteEl.textContent = '–';
    centsEl.textContent = '±0';
    needleEl.style.left = '50%';
    displayEl.classList.remove('in-tune');
    stringButtons.forEach((b) => b.classList.remove('active'));
  }

  function update() {
    if (!listening || !analyser) return;
    analyser.getFloatTimeDomainData(buffer);
    const freq = autoCorrelate(buffer, getCtx().sampleRate);

    if (freq > 0) {
      const midiFloat = freqToMidi(freq);
      const midi = Math.round(midiFloat);
      const cents = Math.round((midiFloat - midi) * 100);
      const name = NOTE_NAMES[((midi % 12) + 12) % 12];
      const octave = Math.floor(midi / 12) - 1;

      noteEl.textContent = `${name}${octave}`;
      centsEl.textContent = `${cents > 0 ? '+' : ''}${cents}`;
      needleEl.style.left = `${50 + Math.max(-50, Math.min(50, cents))}%`;
      displayEl.classList.toggle('in-tune', Math.abs(cents) <= 5);

      stringButtons.forEach((b) => b.classList.toggle('active', Number(b.dataset.midi) === midi));
    }
    rafId = requestAnimationFrame(update);
  }

  startBtn.addEventListener('click', () => {
    if (listening) stopMic(); else startMic();
  });

  // Cleanup when the user navigates away.
  return function cleanup() {
    stopMic();
    if (audioCtx) { audioCtx.close(); audioCtx = null; }
  };
}
