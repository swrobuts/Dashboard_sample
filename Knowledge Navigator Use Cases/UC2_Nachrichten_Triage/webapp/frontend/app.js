// webapp/frontend/app.js
'use strict';

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  exchangeConnected: false,
  currentAudio: null,
};

// ── DOM Refs ──────────────────────────────────────────────────────────────
const phil          = document.getElementById('phil');
const speechText    = document.getElementById('speech-text');
const speechBubble  = document.getElementById('speech-bubble');
const audioControls = document.getElementById('audio-controls');
const audioPlayer   = document.getElementById('audio-player');
const waveformCanvas = document.getElementById('waveform');

const tabs          = document.querySelectorAll('.tab');
const panels        = document.querySelectorAll('.tab-panel');

const emailInput    = document.getElementById('email-input');
const btnAnalyze    = document.getElementById('btn-analyze');
const resultsEl     = document.getElementById('results');

// Exchange
const credentialForm   = document.getElementById('credential-form');
const connectedState   = document.getElementById('connected-state');
const connectedInfo    = document.getElementById('connected-info');
const btnConnect       = document.getElementById('btn-connect');
const btnDisconnect    = document.getElementById('btn-disconnect');
const btnLiveTriage    = document.getElementById('btn-live-triage');

// Audio buttons
const btnPlay  = document.getElementById('btn-play');
const btnPause = document.getElementById('btn-pause');
const btnStop  = document.getElementById('btn-stop');

// ── Helpers ───────────────────────────────────────────────────────────────
function setPhilState(s) {
  phil.dataset.state = s;
}

let _typewriterTimer = null;
function typewrite(text, delay = 20) {
  speechText.textContent = '';
  clearTimeout(_typewriterTimer);
  let i = 0;
  function step() {
    if (i < text.length) {
      speechText.textContent += text[i++];
      _typewriterTimer = setTimeout(step, delay);
    }
  }
  step();
}

function philSay(text) {
  typewrite(text);
}

// ── Kategorie → CSS-Klasse + Emoji ───────────────────────────────────────
const KATEGORIE_META = {
  'VIP':          { cls: 'card--vip',        emoji: '🔴', label: 'VIP' },
  'Aktion nötig': { cls: 'card--aktion',     emoji: '🟡', label: 'Aktion nötig' },
  'Nur Info':     { cls: 'card--info',       emoji: '🔵', label: 'Nur Info' },
  'Ignorieren':   { cls: 'card--ignorieren', emoji: '⚫', label: 'Ignorieren' },
};

// ── Karte rendern ─────────────────────────────────────────────────────────
function renderCard(result, index, emailPreview = '') {
  const meta = KATEGORIE_META[result.kategorie] ?? KATEGORIE_META['Ignorieren'];
  const card = document.createElement('div');
  card.className = `card ${meta.cls}`;
  card.style.animationDelay = `${index * 80}ms`;

  // Sprechtext für TTS
  const ttsText =
    `${meta.label}. Priorität ${result.priorität}. ` +
    `${result.zusammenfassung} ` +
    `Empfehlung: ${result.empfohlene_aktion}`;

  card.innerHTML = `
    <div class="card__header" role="button" tabindex="0"
         aria-expanded="false" aria-controls="card-detail-${index}">
      <span class="card__prio">${meta.emoji} ${meta.label} · ${result.priorität}/4</span>
      <span class="card__summary">${escHtml(result.zusammenfassung)}</span>
      <button class="card__play-btn" aria-label="Vorlesen" data-tts="${escAttr(ttsText)}">▶</button>
    </div>
    <div class="card__details" id="card-detail-${index}" role="region">
      <div class="card__details-inner">
        <span class="card__detail-label">Empfehlung</span>
        <span class="card__detail-value">${escHtml(result.empfohlene_aktion)}</span>
        ${emailPreview ? `<span class="card__meta">Vorschau: ${escHtml(emailPreview.slice(0, 100))}…</span>` : ''}
      </div>
    </div>
  `;

  // Expand/Collapse
  const header  = card.querySelector('.card__header');
  const details = card.querySelector('.card__details');
  header.addEventListener('click', (e) => {
    if (e.target.closest('.card__play-btn')) return;
    const open = details.classList.toggle('card__details--open');
    header.setAttribute('aria-expanded', open);
  });
  header.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      header.click();
    }
  });

  // Play-Button
  card.querySelector('.card__play-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    const text = e.currentTarget.dataset.tts;
    playTTS(text);
  });

  return card;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escAttr(s) { return escHtml(s); }

// ── API ───────────────────────────────────────────────────────────────────
async function apiAnalyze(emailText) {
  const res = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email_text: emailText }),
  });
  if (!res.ok) throw new Error(`Analyse fehlgeschlagen (${res.status})`);
  return res.json();
}

async function apiTTS(text) {
  const res = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`TTS fehlgeschlagen (${res.status})`);
  return res.blob();
}

// ── TTS Playback ──────────────────────────────────────────────────────────
async function playTTS(text) {
  try {
    setPhilState('thinking');
    const blob = await apiTTS(text);
    const url  = URL.createObjectURL(blob);

    if (state.currentAudio) {
      URL.revokeObjectURL(state.currentAudio);
    }
    state.currentAudio = url;

    audioPlayer.src = url;
    audioPlayer.play();
    audioControls.hidden = false;
    drawWaveformIdle();
  } catch (err) {
    setPhilState('idle');
    console.error('TTS error:', err);
  }
}

audioPlayer.addEventListener('play',  () => { setPhilState('speaking'); drawWaveformAnimated(); });
audioPlayer.addEventListener('pause', () => { setPhilState('idle');     stopWaveform(); });
audioPlayer.addEventListener('ended', () => {
  setPhilState('done');
  setTimeout(() => setPhilState('idle'), 400);
  stopWaveform();
});

btnPlay.addEventListener('click',  () => audioPlayer.play());
btnPause.addEventListener('click', () => audioPlayer.pause());
btnStop.addEventListener('click',  () => { audioPlayer.pause(); audioPlayer.currentTime = 0; });

// ── Waveform (Canvas, simpel) ─────────────────────────────────────────────
let _waveAnim = null;
const waveCtx = waveformCanvas.getContext('2d');

function drawWaveformIdle() {
  waveCtx.clearRect(0, 0, 120, 32);
  waveCtx.fillStyle = getComputedStyle(document.documentElement)
    .getPropertyValue('--text-muted').trim();
  for (let x = 4; x < 116; x += 6) {
    waveCtx.fillRect(x, 14, 3, 4);
  }
}

function drawWaveformAnimated() {
  stopWaveform();
  function frame() {
    waveCtx.clearRect(0, 0, 120, 32);
    waveCtx.fillStyle = '#18181B';
    const t = Date.now() / 200;
    for (let i = 0; i < 18; i++) {
      const x = 4 + i * 6.5;
      const h = 4 + Math.abs(Math.sin(t + i * 0.8)) * 18;
      waveCtx.fillRect(x, 16 - h / 2, 3, h);
    }
    _waveAnim = requestAnimationFrame(frame);
  }
  frame();
}

function stopWaveform() {
  if (_waveAnim) { cancelAnimationFrame(_waveAnim); _waveAnim = null; }
  drawWaveformIdle();
}

// ── Tab-Switching ─────────────────────────────────────────────────────────
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => { t.classList.remove('tab--active'); t.setAttribute('aria-selected', 'false'); });
    panels.forEach(p => p.classList.add('tab-panel--hidden'));

    tab.classList.add('tab--active');
    tab.setAttribute('aria-selected', 'true');
    const targetId = `panel-${tab.dataset.tab}`;
    document.getElementById(targetId).classList.remove('tab-panel--hidden');
  });
});

// ── Paste-Modus: Analyse ──────────────────────────────────────────────────
btnAnalyze.addEventListener('click', async () => {
  const text = emailInput.value.trim();
  if (!text) {
    philSay('Bitte zuerst einen E-Mail-Text einfügen.');
    return;
  }

  btnAnalyze.disabled = true;
  btnAnalyze.innerHTML = '<span class="spinner"></span> Analysiere…';
  setPhilState('thinking');
  philSay('Ich analysiere die E-Mail…');
  resultsEl.innerHTML = '';

  try {
    const result = await apiAnalyze(text);
    resultsEl.appendChild(renderCard(result, 0, text));

    const summary =
      `Analyse abgeschlossen. Kategorie: ${result.kategorie}. ` +
      `${result.zusammenfassung}`;
    philSay(summary);
    await playTTS(summary);
  } catch (err) {
    philSay(`Fehler: ${err.message}`);
    setPhilState('idle');
  } finally {
    btnAnalyze.disabled = false;
    btnAnalyze.innerHTML = 'Analysieren';
  }
});

// ── Exchange API ──────────────────────────────────────────────────────────
async function apiConnect(username, password, institution) {
  const res = await fetch('/api/exchange/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, institution }),
    credentials: 'same-origin',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Verbindung fehlgeschlagen' }));
    throw new Error(err.detail ?? 'Verbindung fehlgeschlagen');
  }
  return res.json();
}

async function apiDisconnect() {
  await fetch('/api/exchange/disconnect', {
    method: 'POST',
    credentials: 'same-origin',
  });
}

async function apiFetch(maxCount, unreadOnly) {
  const res = await fetch('/api/exchange/fetch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ max_count: maxCount, unread_only: unreadOnly }),
    credentials: 'same-origin',
  });
  if (!res.ok) throw new Error('Fetch fehlgeschlagen — bitte erneut verbinden.');
  return res.json();
}

// ── Institution Placeholder ───────────────────────────────────────────────
const usernameInput   = document.getElementById('username');
const institutionSel  = document.getElementById('institution');
const INSTITUTION_HINTS = {
  THWS: 'vorname.nachname',
  DHBW: 'vollstaendige@email.de',
};
institutionSel.addEventListener('change', () => {
  usernameInput.placeholder = INSTITUTION_HINTS[institutionSel.value] ?? '';
  usernameInput.value = '';
});

// ── Connect ───────────────────────────────────────────────────────────────
credentialForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const username    = usernameInput.value.trim();
  const password    = document.getElementById('password').value;
  const institution = institutionSel.value;

  if (!username || !password) {
    philSay('Bitte Benutzername und Passwort eingeben.');
    return;
  }

  btnConnect.disabled = true;
  btnConnect.innerHTML = '<span class="spinner"></span> Verbinde…';
  setPhilState('thinking');
  philSay('Verbinde mit Exchange…');

  try {
    const data = await apiConnect(username, password, institution);
    state.exchangeConnected = true;

    // Passwort sofort löschen
    document.getElementById('password').value = '';

    credentialForm.hidden  = true;
    connectedState.hidden  = false;
    connectedInfo.textContent =
      `✓ Verbunden mit ${institution} · ${data.inbox_count} Mails im Posteingang`;

    const msg = `Verbindung hergestellt. Sie haben ${data.inbox_count} Mails.`;
    philSay(msg);
    await playTTS(msg);
  } catch (err) {
    philSay(`Verbindung fehlgeschlagen: ${err.message}`);
    setPhilState('idle');
  } finally {
    btnConnect.disabled = false;
    btnConnect.innerHTML = 'Verbinden';
  }
});

// ── Disconnect ────────────────────────────────────────────────────────────
btnDisconnect.addEventListener('click', async () => {
  await apiDisconnect();
  state.exchangeConnected = false;
  credentialForm.hidden = false;
  connectedState.hidden = true;
  resultsEl.innerHTML   = '';
  philSay('Verbindung getrennt.');
});

// ── Live-Triage ───────────────────────────────────────────────────────────
btnLiveTriage.addEventListener('click', async () => {
  const maxCount  = parseInt(document.getElementById('max-count').value, 10) || 10;
  const unreadOnly = document.getElementById('unread-only').checked;

  btnLiveTriage.disabled = true;
  btnLiveTriage.innerHTML = '<span class="spinner"></span> Lade Mails…';
  setPhilState('thinking');
  philSay('Lade E-Mails aus dem Postfach…');
  resultsEl.innerHTML = '';

  try {
    const { emails, skipped } = await apiFetch(maxCount, unreadOnly);

    if (emails.length === 0) {
      philSay('Keine E-Mails gefunden.');
      setPhilState('idle');
      return;
    }

    philSay(`Analysiere ${emails.length} E-Mail${emails.length !== 1 ? 's' : ''}…`);

    const results = [];
    for (const email of emails) {
      const emailText =
        `Von: ${email.sender}\nBetreff: ${email.subject}\n\n${email.body ?? ''}`;
      const result = await apiAnalyze(emailText);
      results.push({ result, email });
    }

    results.forEach(({ result, email }, i) => {
      resultsEl.appendChild(renderCard(result, i, email.subject));
    });

    const vipCount    = results.filter(r => r.result.kategorie === 'VIP').length;
    const aktionCount = results.filter(r => r.result.kategorie === 'Aktion nötig').length;
    const parts = [];
    if (vipCount)    parts.push(`${vipCount} VIP-Mail${vipCount !== 1 ? 's' : ''}`);
    if (aktionCount) parts.push(`${aktionCount} Aktion nötig`);
    const summary = parts.length
      ? `Analyse abgeschlossen. ${parts.join(', ')} — sofortige Aufmerksamkeit erforderlich.`
      : `Analyse abgeschlossen. Keine dringenden Mails.`;

    if (skipped > 0) {
      const notice = document.createElement('p');
      notice.style.cssText = 'font-size:.8125rem;color:var(--text-muted);margin-top:8px';
      notice.textContent = `⚠ ${skipped} Mail${skipped !== 1 ? 's' : ''} konnten nicht geladen werden.`;
      resultsEl.appendChild(notice);
    }

    philSay(summary);
    await playTTS(summary);
  } catch (err) {
    philSay(`Fehler: ${err.message}`);
    setPhilState('idle');
  } finally {
    btnLiveTriage.disabled = false;
    btnLiveTriage.innerHTML = 'Live-Triage starten';
  }
});
