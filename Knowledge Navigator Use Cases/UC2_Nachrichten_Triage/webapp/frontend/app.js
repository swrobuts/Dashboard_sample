// webapp/frontend/app.js
'use strict';

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  user: null,           // {username, institution}
  mails: [],            // raw exchange mails
  triaged: [],          // [{...mail, kategorie, priorität, zusammenfassung, empfohlene_aktion}]
  calendar: [],         // calendar items
  tasks: [],            // task items
  currentView: 'dashboard',
  mailFilter: 'all',
  chatMessages: [],
  philAudio: null,
};

// ── Utils ─────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fmt(iso) {
  if (!iso) return '?';
  try {
    return new Date(iso).toLocaleString('de-DE', {
      weekday: 'short', day: '2-digit', month: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function fmtDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch { return iso; }
}

// ── Init ──────────────────────────────────────────────────────────────────
async function init() {
  try {
    const me = await fetch('/api/auth/me', { credentials: 'same-origin' });
    if (me.ok) {
      state.user = await me.json();
      showApp();
      loadAllData();
    } else {
      showLogin();
    }
  } catch {
    showLogin();
  }
}

function showLogin() {
  document.getElementById('login-screen').hidden = false;
  document.getElementById('app').hidden = true;
}

function showApp() {
  document.getElementById('login-screen').hidden = true;
  document.getElementById('app').hidden = false;
}

// ── Login ─────────────────────────────────────────────────────────────────
document.getElementById('login-institution').addEventListener('change', (e) => {
  const hints = { THWS: 'vorname.nachname', DHBW: 'vollstaendige@email.de' };
  document.getElementById('login-username').placeholder = hints[e.target.value] ?? 'Benutzername';
  document.getElementById('login-username').value = '';
});

document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn-login');
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const institution = document.getElementById('login-institution').value;
  const lockoutMsg = document.getElementById('lockout-msg');

  if (!username || !password) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Verbinde…';
  lockoutMsg.hidden = true;

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, institution }),
      credentials: 'same-origin',
    });

    if (res.status === 429) {
      const data = await res.json();
      const detail = data.detail ?? data;
      const mins = Math.ceil((detail.retry_after ?? 300) / 60);
      lockoutMsg.textContent = `Zu viele Fehlversuche. Bitte ${mins} Minute(n) warten.`;
      lockoutMsg.hidden = false;
    } else if (!res.ok) {
      lockoutMsg.textContent = 'Ungültige Anmeldedaten. Bitte erneut versuchen.';
      lockoutMsg.hidden = false;
    } else {
      const data = await res.json();
      state.user = { username: data.username, institution };
      document.getElementById('login-password').value = '';
      showApp();
      loadAllData();
    }
  } catch {
    lockoutMsg.textContent = 'Verbindungsfehler. Bitte prüfen Sie Ihre Netzwerkverbindung.';
    lockoutMsg.hidden = false;
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Anmelden';
  }
});

// ── Data Loading ──────────────────────────────────────────────────────────
async function loadAllData() {
  try {
    const [calRes, tasksRes, mailsRes] = await Promise.all([
      fetch('/api/calendar', { credentials: 'same-origin' }),
      fetch('/api/tasks', { credentials: 'same-origin' }),
      fetch('/api/exchange/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_count: 50, unread_only: false }),
        credentials: 'same-origin',
      }),
    ]);

    if (calRes.ok) state.calendar = (await calRes.json()).items ?? [];
    if (tasksRes.ok) state.tasks = (await tasksRes.json()).tasks ?? [];
    if (mailsRes.ok) {
      const d = await mailsRes.json();
      state.mails = d.emails ?? [];
      if (state.mails.length && '_skipped' in state.mails[state.mails.length - 1]) {
        state.mails = state.mails.slice(0, -1);
      }
    }
  } catch { /* best effort */ }

  renderDashboard();
  renderCalendarView();
  renderTasksView();

  // Triage up to 20 mails in the background
  triageMails();
}

// ── Triage ────────────────────────────────────────────────────────────────
const KATEGORIE_CSS = {
  'VIP': 'vip',
  'Aktion nötig': 'aktion',
  'Nur Info': 'info',
  'Ignorieren': 'ignorieren',
};

async function triageMails() {
  const toTriage = state.mails.slice(0, 20);
  state.triaged = [];

  for (const mail of toTriage) {
    try {
      const emailText = `Von: ${mail.sender}\nBetreff: ${mail.subject}\n\n${mail.body ?? ''}`;
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email_text: emailText }),
        credentials: 'same-origin',
      });
      if (res.ok) {
        const analysis = await res.json();
        state.triaged.push({ ...mail, ...analysis });
        updateTileCounts();
        renderMailsView();
      }
    } catch { /* skip failed */ }
  }
}

function updateTileCounts() {
  const counts = { VIP: 0, 'Aktion nötig': 0, 'Nur Info': 0, Ignorieren: 0 };
  for (const t of state.triaged) counts[t.kategorie] = (counts[t.kategorie] ?? 0) + 1;
  document.getElementById('count-vip').textContent = counts.VIP;
  document.getElementById('count-aktion').textContent = counts['Aktion nötig'];
  document.getElementById('count-info').textContent = counts['Nur Info'];
  document.getElementById('count-ignorieren').textContent = counts.Ignorieren;
}

// ── Dashboard Render ──────────────────────────────────────────────────────
function renderDashboard() {
  updateTileCounts();

  // Calendar widget — today & tomorrow
  const now = new Date();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 2);
  const calPreview = document.getElementById('calendar-preview');
  const todayItems = state.calendar.filter(c => {
    if (!c.start) return false;
    const d = new Date(c.start);
    return d >= now && d < tomorrow;
  }).slice(0, 4);

  if (todayItems.length === 0) {
    calPreview.innerHTML = '<p class="widget-empty">Keine Termine heute oder morgen.</p>';
  } else {
    calPreview.innerHTML = todayItems.map(c => `
      <div class="widget-item">
        <span class="widget-item-dot"></span>
        <div class="widget-item-text">
          <div class="widget-item-title">${esc(c.subject)}</div>
          <div class="widget-item-meta">${fmt(c.start)}${c.location ? ` · ${esc(c.location)}` : ''}</div>
        </div>
      </div>`).join('');
  }

  // Tasks widget — top 5
  const tasksPreview = document.getElementById('tasks-preview');
  const topTasks = state.tasks.slice(0, 5);
  if (topTasks.length === 0) {
    tasksPreview.innerHTML = '<p class="widget-empty">Keine offenen Aufgaben.</p>';
  } else {
    tasksPreview.innerHTML = topTasks.map(t => `
      <div class="widget-item">
        <span class="widget-item-dot widget-item-dot--task"></span>
        <div class="widget-item-text">
          <div class="widget-item-title">${esc(t.subject)}</div>
          <div class="widget-item-meta">${t.due_date ? `Fällig: ${fmtDate(t.due_date)}` : 'Kein Datum'}</div>
        </div>
      </div>`).join('');
  }
}

// ── Mails View Render ─────────────────────────────────────────────────────
function renderMailsView() {
  const list = document.getElementById('mails-list');
  let items = state.triaged;

  if (state.mailFilter !== 'all') {
    items = items.filter(m => m.kategorie === state.mailFilter);
  }

  if (items.length === 0) {
    list.innerHTML = '<div class="empty-state"><span class="empty-icon">✉</span><span>Keine Mails in dieser Kategorie.</span></div>';
    return;
  }

  list.innerHTML = '';
  items.forEach((m, i) => {
    const cls = KATEGORIE_CSS[m.kategorie] ?? 'ignorieren';
    const card = document.createElement('div');
    card.className = `mail-card mail-card--${cls}`;
    card.style.animationDelay = `${i * 40}ms`;

    const ttsText = `${m.kategorie}. ${m.zusammenfassung} Empfehlung: ${m.empfohlene_aktion}`;
    card.innerHTML = `
      <div class="mail-card__header">
        <span class="mail-card__badge">${esc(m.kategorie)}</span>
        <div class="mail-card__body">
          <div class="mail-card__subject">${esc(m.subject)}</div>
          <div class="mail-card__sender">${esc(m.sender)}</div>
          <div class="mail-card__summary">${esc(m.zusammenfassung)}</div>
        </div>
      </div>
      <div class="mail-card__detail">
        <div class="mail-card__actions">
          <button class="btn btn--ghost btn--sm js-tts" data-tts="${esc(ttsText)}">▶ Vorlesen</button>
          <span style="flex:1"></span>
          <span style="font-size:.8125rem;color:var(--text-muted)">${esc(m.empfohlene_aktion)}</span>
        </div>
      </div>`;

    card.querySelector('.mail-card__header').addEventListener('click', () => {
      const detail = card.querySelector('.mail-card__detail');
      detail.classList.toggle('mail-card__detail--open');
    });
    card.querySelector('.js-tts').addEventListener('click', (e) => {
      e.stopPropagation();
      playTTS(e.currentTarget.dataset.tts);
    });
    list.appendChild(card);
  });
}

// ── Calendar View Render ──────────────────────────────────────────────────
function renderCalendarView() {
  const list = document.getElementById('calendar-list');
  if (state.calendar.length === 0) {
    list.innerHTML = '<div class="empty-state"><span class="empty-icon">⊡</span><span>Keine Termine in den nächsten 14 Tagen.</span></div>';
    return;
  }
  list.innerHTML = state.calendar.map((c, i) => `
    <div class="cal-item" style="animation-delay:${i * 30}ms">
      <div class="cal-item__date">${fmt(c.start)}</div>
      <div class="cal-item__title">${esc(c.subject)}</div>
      <div class="cal-item__meta">
        ${c.location ? esc(c.location) + ' · ' : ''}
        bis ${fmt(c.end)}
        ${c.is_recurring ? ' · wiederkehrend' : ''}
      </div>
    </div>`).join('');
}

// ── Tasks View Render ─────────────────────────────────────────────────────
function renderTasksView() {
  const list = document.getElementById('tasks-list');
  if (state.tasks.length === 0) {
    list.innerHTML = '<div class="empty-state"><span class="empty-icon">✓</span><span>Keine offenen Aufgaben.</span></div>';
    return;
  }
  list.innerHTML = '';
  state.tasks.forEach((t, i) => {
    const prio = t.priority === 'High' ? 'High' : t.priority === 'Low' ? 'Low' : 'Normal';
    const item = document.createElement('div');
    item.className = 'task-item';
    item.style.animationDelay = `${i * 30}ms`;
    item.innerHTML = `
      <button class="task-check" data-id="${esc(t.id)}" data-ck="${esc(t.changekey)}" title="Als erledigt markieren">✓</button>
      <div class="task-item__body">
        <span class="task-priority task-priority--${prio}">${esc(t.priority)}</span>
        <div class="task-item__title">${esc(t.subject)}</div>
        <div class="task-item__meta">${t.due_date ? 'Fällig: ' + fmtDate(t.due_date) : 'Kein Datum'}</div>
      </div>`;
    item.querySelector('.task-check').addEventListener('click', async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await fetch(`/api/tasks/${encodeURIComponent(btn.dataset.id)}/complete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ changekey: btn.dataset.ck }),
          credentials: 'same-origin',
        });
        state.tasks = state.tasks.filter(x => x.id !== btn.dataset.id);
        renderTasksView();
        renderDashboard();
      } catch { btn.disabled = false; }
    });
    list.appendChild(item);
  });
}

// ── View Switching ────────────────────────────────────────────────────────
function switchView(viewName) {
  document.querySelectorAll('.view').forEach(v => v.classList.add('view--hidden'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('nav-item--active'));
  document.getElementById(`view-${viewName}`)?.classList.remove('view--hidden');
  document.querySelector(`[data-view="${viewName}"]`)?.classList.add('nav-item--active');
  state.currentView = viewName;
}

document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

// Tile click → go to mails filtered
document.querySelectorAll('.tile').forEach(tile => {
  tile.addEventListener('click', () => {
    state.mailFilter = tile.dataset.filter;
    document.querySelectorAll('.pill').forEach(p => p.classList.remove('pill--active'));
    document.querySelector(`.pill[data-cat="${tile.dataset.filter}"]`)?.classList.add('pill--active');
    switchView('mails');
    renderMailsView();
  });
});

// Mail filter pills
document.querySelectorAll('.pill').forEach(pill => {
  pill.addEventListener('click', () => {
    document.querySelectorAll('.pill').forEach(p => p.classList.remove('pill--active'));
    pill.classList.add('pill--active');
    state.mailFilter = pill.dataset.cat;
    renderMailsView();
  });
});

// ── Phil Chat Panel ───────────────────────────────────────────────────────
const chatPanel = document.getElementById('phil-chat');
const chatBackdrop = document.getElementById('chat-backdrop');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');

function openChat() {
  chatPanel.classList.add('chat-panel--open');
  chatPanel.setAttribute('aria-hidden', 'false');
  chatBackdrop.classList.remove('backdrop--hidden');
  chatInput.focus();
}

function closeChat() {
  chatPanel.classList.remove('chat-panel--open');
  chatPanel.setAttribute('aria-hidden', 'true');
  chatBackdrop.classList.add('backdrop--hidden');
}

document.getElementById('btn-phil-chat').addEventListener('click', openChat);
document.getElementById('btn-close-chat').addEventListener('click', closeChat);
chatBackdrop.addEventListener('click', closeChat);

function appendChatMessage(role, text) {
  const div = document.createElement('div');
  div.className = `chat-msg chat-msg--${role}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

async function sendChatMessage() {
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = '';
  appendChatMessage('user', text);

  const philMsg = appendChatMessage('phil', '');
  const spinner = document.createElement('span');
  spinner.className = 'spinner spinner--dark';
  philMsg.appendChild(spinner);

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, include_context: true }),
      credentials: 'same-origin',
    });

    if (!resp.ok) {
      philMsg.textContent = 'Fehler beim Abrufen der Antwort.';
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    philMsg.textContent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') break;
          philMsg.textContent += data;
          chatMessages.scrollTop = chatMessages.scrollHeight;
        }
      }
    }

    if (philMsg.textContent) {
      playTTS(philMsg.textContent.slice(0, 400));
    }
  } catch {
    philMsg.textContent = 'Verbindungsfehler.';
  }
}

document.getElementById('btn-chat-send').addEventListener('click', sendChatMessage);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
});

// ── Settings Modal ────────────────────────────────────────────────────────
const settingsModal = document.getElementById('settings-modal');
const modalBackdrop = document.getElementById('modal-backdrop');

function openSettings() {
  document.getElementById('settings-info').innerHTML = `
    <p><strong>Angemeldet als:</strong> ${esc(state.user?.username ?? '—')}</p>
    <p><strong>Institution:</strong> ${esc(state.user?.institution ?? '—')}</p>
    <p><strong>Mails:</strong> ${state.mails.length} geladen, ${state.triaged.length} analysiert</p>`;
  settingsModal.classList.remove('modal--hidden');
  modalBackdrop.classList.remove('backdrop--hidden');
  modalBackdrop.style.zIndex = '290';
}

function closeSettings() {
  settingsModal.classList.add('modal--hidden');
  modalBackdrop.classList.add('backdrop--hidden');
}

document.getElementById('btn-settings').addEventListener('click', openSettings);
document.getElementById('btn-close-settings').addEventListener('click', closeSettings);
modalBackdrop.addEventListener('click', () => {
  closeSettings();
  closeEventModal();
  closeTaskModal();
});

document.getElementById('btn-logout').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
  location.reload();
});

document.getElementById('btn-reload-mails').addEventListener('click', async () => {
  closeSettings();
  state.mails = [];
  state.triaged = [];
  state.calendar = [];
  state.tasks = [];
  renderDashboard();
  renderMailsView();
  renderCalendarView();
  renderTasksView();
  await loadAllData();
});

// ── Create Event Modal ────────────────────────────────────────────────────
const eventModal = document.getElementById('event-modal');
const formBackdrop = document.getElementById('form-backdrop');

function openEventModal() {
  eventModal.classList.remove('modal--hidden');
  formBackdrop.classList.remove('backdrop--hidden');
  formBackdrop.style.zIndex = '290';
  document.getElementById('event-subject').focus();
}

function closeEventModal() {
  eventModal.classList.add('modal--hidden');
  formBackdrop.classList.add('backdrop--hidden');
}

document.getElementById('btn-add-event').addEventListener('click', openEventModal);
document.getElementById('btn-close-event').addEventListener('click', closeEventModal);

document.getElementById('event-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn-save-event');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Speichern…';

  try {
    const res = await fetch('/api/calendar/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject: document.getElementById('event-subject').value.trim(),
        start: document.getElementById('event-start').value,
        end: document.getElementById('event-end').value,
        location: document.getElementById('event-location').value.trim(),
        body: document.getElementById('event-body').value.trim(),
      }),
      credentials: 'same-origin',
    });
    if (res.ok) {
      closeEventModal();
      document.getElementById('event-form').reset();
      // Reload calendar
      const calRes = await fetch('/api/calendar', { credentials: 'same-origin' });
      if (calRes.ok) {
        state.calendar = (await calRes.json()).items ?? [];
        renderCalendarView();
        renderDashboard();
      }
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Speichern';
  }
});

// ── Create Task Modal ─────────────────────────────────────────────────────
const taskModal = document.getElementById('task-modal');

function openTaskModal() {
  taskModal.classList.remove('modal--hidden');
  formBackdrop.classList.remove('backdrop--hidden');
  formBackdrop.style.zIndex = '290';
  document.getElementById('task-subject').focus();
}

function closeTaskModal() {
  taskModal.classList.add('modal--hidden');
  formBackdrop.classList.add('backdrop--hidden');
}

document.getElementById('btn-add-task').addEventListener('click', openTaskModal);
document.getElementById('btn-close-task').addEventListener('click', closeTaskModal);

document.getElementById('task-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn-save-task');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Speichern…';

  try {
    const res = await fetch('/api/tasks/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject: document.getElementById('task-subject').value.trim(),
        due_date: document.getElementById('task-due').value || null,
        priority: document.getElementById('task-priority').value,
        body: document.getElementById('task-body').value.trim(),
      }),
      credentials: 'same-origin',
    });
    if (res.ok) {
      closeTaskModal();
      document.getElementById('task-form').reset();
      const tasksRes = await fetch('/api/tasks', { credentials: 'same-origin' });
      if (tasksRes.ok) {
        state.tasks = (await tasksRes.json()).tasks ?? [];
        renderTasksView();
        renderDashboard();
      }
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Speichern';
  }
});

// ── TTS ───────────────────────────────────────────────────────────────────
const audioPlayer = document.getElementById('audio-player');

async function playTTS(text) {
  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.slice(0, 500) }),
      credentials: 'same-origin',
    });
    if (!res.ok) return;
    const blob = await res.blob();
    if (state.philAudio) URL.revokeObjectURL(state.philAudio);
    state.philAudio = URL.createObjectURL(blob);
    audioPlayer.src = state.philAudio;
    audioPlayer.play().catch(() => {});
  } catch { /* TTS non-critical */ }
}

// ── Start ─────────────────────────────────────────────────────────────────
init();
