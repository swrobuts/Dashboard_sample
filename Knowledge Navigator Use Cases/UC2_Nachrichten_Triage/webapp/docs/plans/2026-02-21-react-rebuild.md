# PHIL PIM Dashboard — React + Vite Rebuild

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the vanilla-JS frontend as a React 18 + TypeScript + Vite SPA with a modern 3-column layout (dark sidebar, content area, persistent PHIL panel), fix EWS parallel login for THWS so calendar/tasks actually load, and keep all 22 backend tests green.

**Architecture:**
- React 18 + TypeScript + Vite — compiled to `frontend/dist/`, served by FastAPI from `/`
- Zustand for global state (user, mails, calendar, tasks, selection)
- CSS Modules — no Tailwind; design tokens in `src/styles/tokens.css`
- 3-column layout desktop: Sidebar 220px (zinc-900 dark) | Content flex-1 (gray-50) | PHIL Panel 360px (white)
- Mobile: single column with bottom nav, PHIL as slide-up sheet
- PHIL Panel is persistent and context-sensitive: shows analysis + actions for selected mail/event/task
- Backend: THWS login attempts EWS in parallel (non-fatal if it fails); session stores both `imap_config` and optional `ews_account`

**Tech Stack:** React 18, TypeScript 5, Vite 5, Zustand 4, CSS Modules, FastAPI (unchanged), exchangelib (unchanged)

---

## Working Directory

All commands run from:
```
UC2_Nachrichten_Triage/webapp/
```

## Environment

Backend `.env` is at `backend/.env` and must contain `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`.

Python venv: activate with `source .venv/bin/activate` (or the project's venv path).

---

## Task 1: Vite + React scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

**Step 1: Scaffold with Vite**

```bash
cd UC2_Nachrichten_Triage/webapp
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install zustand
```

Expected: `frontend/` created with React + TypeScript template.

**Step 2: Configure Vite proxy (dev mode)**

Edit `frontend/vite.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
    },
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
})
```

Note: build output goes to `../static/` so FastAPI can serve it.

**Step 3: Update FastAPI to serve React build**

In `backend/main.py`, replace the current static file mount. Find the `StaticFiles` mount and update it:

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Mount static assets (JS/CSS chunks)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

@app.get("/", include_in_schema=False)
@app.get("/{full_path:path}", include_in_schema=False)
def serve_spa(full_path: str = ""):
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return {"error": "Frontend not built. Run: cd frontend && npm run build"}
```

IMPORTANT: The catch-all route must come AFTER all `/api/` routes.

**Step 4: Add Google Font import to index.html**

In `frontend/index.html`, add inside `<head>`:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
```

**Step 5: Build and verify**

```bash
cd frontend && npm run build
cd ..
python -m pytest tests/ -v
```

Expected: `static/index.html` exists, 22 tests pass. Visit http://localhost:8001/ → shows React app shell.

**Step 6: Commit**

```bash
git add frontend/ backend/main.py static/
git commit -m "feat(frontend): scaffold React+Vite, wire FastAPI to serve dist"
```

---

## Task 2: Design tokens + global CSS + API client

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/reset.css`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/types.ts`

**Step 1: Design tokens**

Create `frontend/src/styles/tokens.css`:

```css
:root {
  /* Brand */
  --amber: #F59E0B;
  --amber-light: #FEF3C7;
  --amber-dark: #D97706;

  /* Sidebar */
  --sidebar-bg: #18181B;
  --sidebar-text: #A1A1AA;
  --sidebar-text-active: #FFFFFF;
  --sidebar-hover: #27272A;
  --sidebar-active: #3F3F46;
  --sidebar-border: #27272A;

  /* Content */
  --content-bg: #FAFAFA;
  --content-border: #E4E4E7;

  /* PHIL Panel */
  --phil-bg: #FFFFFF;
  --phil-border: #E4E4E7;

  /* Cards */
  --card-bg: #FFFFFF;
  --card-border: #E4E4E7;
  --card-shadow: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  --card-shadow-hover: 0 4px 12px rgba(0,0,0,.1);

  /* Category colors */
  --vip-bg: #FEF2F2;
  --vip-text: #DC2626;
  --vip-badge: #EF4444;
  --aktion-bg: #FFFBEB;
  --aktion-text: #D97706;
  --aktion-badge: #F59E0B;
  --info-bg: #EFF6FF;
  --info-text: #2563EB;
  --info-badge: #3B82F6;
  --ignorieren-bg: #F9FAFB;
  --ignorieren-text: #6B7280;
  --ignorieren-badge: #9CA3AF;

  /* Typography */
  --font: 'Instrument Sans', system-ui, sans-serif;
  --text-xs: 0.72rem;
  --text-sm: 0.83rem;
  --text-base: 0.938rem;
  --text-lg: 1.063rem;
  --text-xl: 1.25rem;
  --text-2xl: 1.5rem;

  /* Spacing */
  --radius-sm: 6px;
  --radius: 10px;
  --radius-lg: 14px;
  --radius-xl: 20px;

  /* Layout */
  --sidebar-w: 220px;
  --phil-w: 360px;
  --header-h: 52px;
  --bottom-nav-h: 60px;
  --transition: 200ms cubic-bezier(.4,0,.2,1);
}
```

**Step 2: Reset CSS**

Create `frontend/src/styles/reset.css`:

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-family: var(--font); font-size: 16px; -webkit-font-smoothing: antialiased; }
body { background: var(--content-bg); color: #18181B; }
button { cursor: pointer; border: none; background: none; font: inherit; }
input, textarea, select { font: inherit; outline: none; }
a { color: inherit; text-decoration: none; }
ul, ol { list-style: none; }
```

**Step 3: Import tokens in main.tsx**

```tsx
// frontend/src/main.tsx
import './styles/tokens.css'
import './styles/reset.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>
)
```

**Step 4: API types**

Create `frontend/src/api/types.ts`:

```ts
export interface User {
  username: string
  institution: string
  inbox_count: number
  ews_connected: boolean
}

export type Category = 'VIP' | 'Aktion nötig' | 'Nur Info' | 'Ignorieren'

export interface TriagedMail {
  subject: string
  sender: string
  body: string
  datetime_received: string | null
  is_read: boolean
  // triage fields
  kategorie: Category
  priorität: number
  zusammenfassung: string
  empfohlene_aktion: string
  // ui
  id: string
  triageStatus: 'pending' | 'done' | 'error'
}

export interface CalendarItem {
  id: string
  changekey: string
  subject: string
  start: string | null
  end: string | null
  location: string
  body: string
  is_recurring: boolean
}

export interface Task {
  id: string
  changekey: string
  subject: string
  due_date: string | null
  status: string
  priority: string
  percent_complete: number
  body: string
}
```

**Step 5: API client**

Create `frontend/src/api/client.ts`:

```ts
import type { User, TriagedMail, CalendarItem, Task } from './types'

const BASE = ''  // same origin

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw Object.assign(new Error(err.detail ?? r.statusText), { status: r.status, data: err })
  }
  return r.json()
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path)
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw Object.assign(new Error(err.detail ?? r.statusText), { status: r.status, data: err })
  }
  return r.json()
}

export const api = {
  // Auth
  me: () => get<User>('/api/auth/me'),
  login: (username: string, password: string, institution: string) =>
    post<User & { status: string }>('/api/auth/login', { username, password, institution }),
  logout: () => post<{ status: string }>('/api/auth/logout', {}),

  // Mails
  fetchMails: (max_count = 30, unread_only = false) =>
    post<{ emails: Array<Omit<TriagedMail, 'kategorie' | 'priorität' | 'zusammenfassung' | 'empfohlene_aktion' | 'id' | 'triageStatus'>> }>(
      '/api/exchange/fetch', { max_count, unread_only }),

  // Triage
  analyze: (email_text: string) =>
    post<{ kategorie: string; priorität: number; zusammenfassung: string; empfohlene_aktion: string }>(
      '/api/analyze', { email_text }),

  // Calendar
  calendar: (days_ahead = 14) => get<{ items: CalendarItem[] }>(`/api/calendar?days_ahead=${days_ahead}`),
  createCalendar: (subject: string, start: string, end: string, location?: string, body?: string) =>
    post<{ id: string; subject: string }>('/api/calendar/create', { subject, start, end, location, body }),

  // Tasks
  tasks: () => get<{ tasks: Task[] }>('/api/tasks'),
  createTask: (subject: string, due_date?: string, body?: string, priority?: string) =>
    post<{ id: string; subject: string }>('/api/tasks/create', { subject, due_date, body, priority }),
  completeTask: (task_id: string, changekey: string) =>
    post<{ status: string }>(`/api/tasks/${task_id}/complete`, { changekey }),

  // TTS
  tts: async (text: string): Promise<string> => {
    const r = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!r.ok) throw new Error('TTS failed')
    const blob = await r.blob()
    return URL.createObjectURL(blob)
  },

  // Chat (SSE streaming)
  chatStream: (message: string, include_context = true): ReadableStream<string> => {
    const ctrl = new AbortController()
    return new ReadableStream({
      async start(controller) {
        const r = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message, include_context }),
          signal: ctrl.signal,
        })
        if (!r.ok || !r.body) { controller.close(); return }
        const reader = r.body.getReader()
        const dec = new TextDecoder()
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = dec.decode(value)
          for (const line of chunk.split('\n')) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6)
              if (data === '[DONE]') { controller.close(); return }
              controller.enqueue(data)
            }
          }
        }
        controller.close()
      },
      cancel() { ctrl.abort() },
    })
  },
}
```

**Step 6: Build + verify**

```bash
cd frontend && npm run build && cd ..
python -m pytest tests/ -v
```

Expected: 22 tests green.

**Step 7: Commit**

```bash
git add frontend/src/styles/ frontend/src/api/ frontend/src/main.tsx
git commit -m "feat(frontend): design tokens, reset CSS, typed API client"
```

---

## Task 3: Zustand store

**Files:**
- Create: `frontend/src/store/useStore.ts`

**Step 1: Write store**

Create `frontend/src/store/useStore.ts`:

```ts
import { create } from 'zustand'
import type { User, TriagedMail, CalendarItem, Task, Category } from '../api/types'

type View = 'dashboard' | 'mails' | 'calendar' | 'tasks'
type Selection =
  | { type: 'mail'; item: TriagedMail }
  | { type: 'calendar'; item: CalendarItem }
  | { type: 'task'; item: Task }
  | null

interface AppState {
  // Auth
  user: User | null
  setUser: (u: User | null) => void

  // Data
  mails: TriagedMail[]
  calendar: CalendarItem[]
  tasks: Task[]
  setMails: (m: TriagedMail[]) => void
  updateMail: (id: string, patch: Partial<TriagedMail>) => void
  setCalendar: (c: CalendarItem[]) => void
  setTasks: (t: Task[]) => void
  removeTask: (id: string) => void

  // UI
  view: View
  setView: (v: View) => void
  mailFilter: Category | 'all'
  setMailFilter: (f: Category | 'all') => void
  selection: Selection
  setSelection: (s: Selection) => void

  // Loading
  loadingMails: boolean
  loadingCalendar: boolean
  loadingTasks: boolean
  setLoadingMails: (b: boolean) => void
  setLoadingCalendar: (b: boolean) => void
  setLoadingTasks: (b: boolean) => void
}

export const useStore = create<AppState>((set) => ({
  user: null,
  setUser: (user) => set({ user }),

  mails: [],
  calendar: [],
  tasks: [],
  setMails: (mails) => set({ mails }),
  updateMail: (id, patch) =>
    set((s) => ({ mails: s.mails.map((m) => (m.id === id ? { ...m, ...patch } : m)) })),
  setCalendar: (calendar) => set({ calendar }),
  setTasks: (tasks) => set({ tasks }),
  removeTask: (id) => set((s) => ({ tasks: s.tasks.filter((t) => t.id !== id) })),

  view: 'dashboard',
  setView: (view) => set({ view }),
  mailFilter: 'all',
  setMailFilter: (mailFilter) => set({ mailFilter }),
  selection: null,
  setSelection: (selection) => set({ selection }),

  loadingMails: false,
  loadingCalendar: false,
  loadingTasks: false,
  setLoadingMails: (loadingMails) => set({ loadingMails }),
  setLoadingCalendar: (loadingCalendar) => set({ loadingCalendar }),
  setLoadingTasks: (loadingTasks) => set({ loadingTasks }),
}))
```

**Step 2: Data loading hook**

Create `frontend/src/hooks/useDataLoader.ts`:

```ts
import { api } from '../api/client'
import { useStore } from '../store/useStore'
import type { TriagedMail } from '../api/types'

let triageRunning = false

export function useDataLoader() {
  const {
    setMails, updateMail, setCalendar, setTasks,
    setLoadingMails, setLoadingCalendar, setLoadingTasks,
    user,
  } = useStore()

  async function loadMails() {
    setLoadingMails(true)
    try {
      const { emails } = await api.fetchMails(30, false)
      const initial: TriagedMail[] = emails.map((e, i) => ({
        ...e,
        id: `mail-${i}-${Date.now()}`,
        kategorie: 'Nur Info',
        priorität: 3,
        zusammenfassung: '',
        empfohlene_aktion: '',
        triageStatus: 'pending',
      }))
      setMails(initial)
      // Triage top 20 in parallel (max 5 concurrent)
      if (!triageRunning) {
        triageRunning = true
        const toTriage = initial.slice(0, 20)
        const BATCH = 5
        for (let i = 0; i < toTriage.length; i += BATCH) {
          await Promise.all(
            toTriage.slice(i, i + BATCH).map(async (mail) => {
              try {
                const text = `Von: ${mail.sender}\nBetreff: ${mail.subject}\nDatum: ${mail.datetime_received ?? ''}\n\n${mail.body}`
                const result = await api.analyze(text)
                updateMail(mail.id, {
                  kategorie: result.kategorie as TriagedMail['kategorie'],
                  priorität: result.priorität,
                  zusammenfassung: result.zusammenfassung,
                  empfohlene_aktion: result.empfohlene_aktion,
                  triageStatus: 'done',
                })
              } catch {
                updateMail(mail.id, { triageStatus: 'error' })
              }
            })
          )
        }
        triageRunning = false
      }
    } catch (e) {
      console.error('loadMails', e)
    } finally {
      setLoadingMails(false)
    }
  }

  async function loadCalendar() {
    if (!user?.ews_connected) return
    setLoadingCalendar(true)
    try {
      const { items } = await api.calendar()
      setCalendar(items)
    } catch (e) {
      console.error('loadCalendar', e)
    } finally {
      setLoadingCalendar(false)
    }
  }

  async function loadTasks() {
    if (!user?.ews_connected) return
    setLoadingTasks(true)
    try {
      const { tasks } = await api.tasks()
      setTasks(tasks)
    } catch (e) {
      console.error('loadTasks', e)
    } finally {
      setLoadingTasks(false)
    }
  }

  async function loadAll() {
    await Promise.all([loadMails(), loadCalendar(), loadTasks()])
  }

  return { loadAll, loadMails, loadCalendar, loadTasks }
}
```

**Step 3: Build + verify**

```bash
cd frontend && npm run build && cd ..
python -m pytest tests/ -v
```

Expected: 22 tests green, no TypeScript errors.

**Step 4: Commit**

```bash
git add frontend/src/store/ frontend/src/hooks/
git commit -m "feat(frontend): Zustand store + data loading hooks"
```

---

## Task 4: Backend — EWS parallel login for THWS + /api/auth/me ews_connected

**Files:**
- Modify: `webapp/backend/main.py`

The current THWS login only calls `connect_to_imap`. Calendar/tasks use `_sessions[id]["account"]` which doesn't exist for THWS sessions → 500 errors.

**Step 1: Update login endpoint in main.py**

Find the `/api/auth/login` endpoint. Update the THWS branch to also attempt EWS:

```python
@app.post("/api/auth/login")
def auth_login(req: ConnectRequest, request: Request):
    ip = request.client.host
    _check_lockout(ip)

    inst = INSTITUTIONS.get(req.institution)
    if not inst:
        raise HTTPException(400, detail=f"Unbekannte Institution: {req.institution}")

    protocol = inst.get("protocol", "ews")
    imap_config = None
    ews_account = None

    if protocol == "imap+ews":
        # THWS: IMAP required, EWS optional
        try:
            imap_config = connect_to_imap(
                req.username, req.password,
                inst["imap_host"], inst.get("imap_port", 993)
            )
        except Exception as e:
            _record_failure(ip)
            raise HTTPException(401, detail="Ungültige Anmeldedaten (IMAP).")
        # EWS parallel — non-fatal
        try:
            ews_account = connect_to_exchange(req.username, req.password, req.institution)
        except Exception:
            ews_account = None  # EWS optional for THWS
        inbox_count = imap_config["inbox_count"]

    else:
        # EWS-only institutions (DHBW etc.)
        try:
            ews_account = connect_to_exchange(req.username, req.password, req.institution)
            inbox_count = ews_account.inbox.total_count
        except Exception:
            _record_failure(ip)
            raise HTTPException(401, detail="Ungültige Anmeldedaten.")

    _reset_lockout(ip)
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "username": req.username,
        "institution": req.institution,
        "imap_config": imap_config,
        "account": ews_account,
    }
    resp = JSONResponse({
        "status": "ok",
        "username": req.username,
        "institution": req.institution,
        "inbox_count": inbox_count,
        "ews_connected": ews_account is not None,
    })
    resp.set_cookie("session_id", session_id, httponly=True, samesite="strict", secure=False)
    return resp
```

**Step 2: Update /api/auth/me to include ews_connected**

Find `auth_me` and update:

```python
@app.get("/api/auth/me")
def auth_me(session_id: str | None = Cookie(default=None)):
    if not session_id or session_id not in _sessions:
        raise HTTPException(401)
    s = _sessions[session_id]
    return {
        "username": s["username"],
        "institution": s["institution"],
        "ews_connected": s.get("account") is not None,
        "inbox_count": s.get("imap_config", {}).get("inbox_count", 0) if s.get("imap_config") else 0,
    }
```

**Step 3: Update _get_account helper to also handle EWS-less THWS**

The `/api/calendar` and `/api/tasks` endpoints use `_get_account`. Keep that as-is — if `account` is None it returns a 503 gracefully.

Update `_get_account`:

```python
def _get_account(session_id: str | None):
    if not session_id or session_id not in _sessions:
        raise HTTPException(401, "Nicht angemeldet.")
    acc = _sessions[session_id].get("account")
    if acc is None:
        raise HTTPException(503, "Exchange/EWS nicht verbunden. Kalender und Aufgaben nicht verfügbar.")
    return acc
```

**Step 4: Update existing exchange/fetch endpoint to handle both IMAP and EWS sessions**

The `/api/exchange/fetch` route should use IMAP if available, else EWS:

```python
@app.post("/api/exchange/fetch")
def exchange_fetch(req: FetchRequest, session_id: str | None = Cookie(default=None)):
    if not session_id or session_id not in _sessions:
        raise HTTPException(401, "Nicht angemeldet.")
    s = _sessions[session_id]
    if s.get("imap_config"):
        emails = fetch_emails_imap(s["imap_config"], req.max_count, req.unread_only)
    elif s.get("account"):
        emails = fetch_emails(s["account"], req.max_count, req.unread_only)
    else:
        raise HTTPException(503, "Kein E-Mail-Zugang verfügbar.")
    return {"emails": [e for e in emails if "_skipped" not in e]}
```

**Step 5: Update test for auth/me to include ews_connected**

In `tests/test_api.py`, the `test_auth_me_with_session` test checks:
```python
assert data["username"] == "robert.butscher"
assert data["institution"] == "THWS"
```
Add:
```python
assert "ews_connected" in data
```

**Step 6: Run tests**

```bash
python -m pytest tests/ -v
```

Expected: 22+ tests green.

**Step 7: Commit**

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat(backend): EWS parallel login for THWS, ews_connected in session"
```

---

## Task 5: App shell — Login screen + root layout

**Files:**
- Create: `frontend/src/components/Login/Login.tsx`
- Create: `frontend/src/components/Login/Login.module.css`
- Create: `frontend/src/components/Layout/AppShell.tsx`
- Create: `frontend/src/components/Layout/AppShell.module.css`
- Modify: `frontend/src/App.tsx`

**Step 1: Login component**

Create `frontend/src/components/Login/Login.tsx`:

```tsx
import { useState } from 'react'
import { api } from '../../api/client'
import { useStore } from '../../store/useStore'
import type { User } from '../../api/types'
import styles from './Login.module.css'

const INSTITUTIONS = ['THWS', 'DHBW']

interface Props { onLogin: (user: User) => void }

export function Login({ onLogin }: Props) {
  const [institution, setInstitution] = useState('THWS')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [lockout, setLockout] = useState(0)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.login(username, password, institution)
      onLogin({
        username: data.username,
        institution: data.institution,
        inbox_count: data.inbox_count,
        ews_connected: data.ews_connected,
      })
    } catch (err: any) {
      if (err.status === 429) {
        setLockout(err.data?.detail?.retry_after ?? 300)
      } else {
        setError('Ungültige Anmeldedaten')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <img src="/phil.png" className={styles.avatar} alt="PHIL" />
        <h1 className={styles.title}>PHIL</h1>
        <p className={styles.subtitle}>Persönlicher Hochschul-Assistent</p>

        <form onSubmit={handleSubmit} className={styles.form} noValidate>
          <select
            className={styles.select}
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
          >
            {INSTITUTIONS.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
          <input
            className={styles.input}
            type="text"
            placeholder="Benutzername"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
          <input
            className={styles.input}
            type="password"
            placeholder="Passwort"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
          {error && <p className={styles.error}>{error}</p>}
          {lockout > 0 && (
            <p className={styles.lockout}>
              Zu viele Fehlversuche. Bitte {Math.ceil(lockout / 60)} Min. warten.
            </p>
          )}
          <button className={styles.btn} type="submit" disabled={loading || lockout > 0}>
            {loading ? 'Verbinde…' : 'Anmelden'}
          </button>
        </form>
        <p className={styles.notice}>Credentials werden nicht gespeichert.</p>
      </div>
    </div>
  )
}
```

Create `frontend/src/components/Login/Login.module.css`:

```css
.screen {
  position: fixed; inset: 0;
  background: var(--sidebar-bg);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font);
}

.card {
  width: min(400px, 92vw);
  background: var(--card-bg);
  border-radius: var(--radius-xl);
  padding: 2.5rem 2rem;
  text-align: center;
  box-shadow: 0 24px 64px rgba(0,0,0,.35);
}

.avatar {
  width: 88px; height: 88px;
  border-radius: 50%;
  margin: 0 auto 1.25rem;
  display: block;
  border: 3px solid var(--amber);
  object-fit: cover;
}

.title {
  font-size: var(--text-2xl); font-weight: 700;
  letter-spacing: -.02em; margin-bottom: .25rem;
}

.subtitle {
  color: #6B7280; font-size: var(--text-sm);
  margin-bottom: 2rem;
}

.form { display: flex; flex-direction: column; gap: .75rem; }

.select, .input {
  width: 100%; padding: .7rem 1rem;
  border: 1.5px solid var(--content-border);
  border-radius: var(--radius);
  font-size: var(--text-base);
  transition: border-color var(--transition);
  background: var(--content-bg);
}
.select:focus, .input:focus { border-color: var(--amber); }

.error { color: var(--vip-text); font-size: var(--text-sm); }
.lockout { color: var(--aktion-text); font-size: var(--text-sm); }

.btn {
  padding: .8rem;
  background: var(--amber);
  color: white;
  border-radius: var(--radius);
  font-weight: 600; font-size: var(--text-base);
  transition: background var(--transition), transform var(--transition);
  margin-top: .25rem;
}
.btn:hover:not(:disabled) { background: var(--amber-dark); transform: translateY(-1px); }
.btn:disabled { opacity: .6; cursor: not-allowed; }

.notice {
  margin-top: 1.5rem; font-size: var(--text-xs); color: #9CA3AF;
}
```

**Step 2: App shell layout**

Create `frontend/src/components/Layout/AppShell.tsx`:

```tsx
import { useState } from 'react'
import { useStore } from '../../store/useStore'
import { Sidebar } from './Sidebar'
import { PhilPanel } from '../Phil/PhilPanel'
import styles from './AppShell.module.css'

interface Props { children: React.ReactNode }

export function AppShell({ children }: Props) {
  const [philOpen, setPhilOpen] = useState(false)

  return (
    <div className={styles.shell}>
      <Sidebar onOpenPhil={() => setPhilOpen(true)} />
      <main className={styles.content}>{children}</main>
      <PhilPanel open={philOpen} onClose={() => setPhilOpen(false)} />
      {philOpen && (
        <div className={styles.backdrop} onClick={() => setPhilOpen(false)} />
      )}
    </div>
  )
}
```

Create `frontend/src/components/Layout/AppShell.module.css`:

```css
.shell {
  display: grid;
  grid-template-columns: var(--sidebar-w) 1fr;
  grid-template-rows: 100vh;
  height: 100vh;
  overflow: hidden;
}

.content {
  overflow-y: auto;
  background: var(--content-bg);
  padding-bottom: 2rem;
}

/* Desktop: 3-column when PHIL panel open */
@media (min-width: 800px) {
  .shell[data-phil-open="true"] {
    grid-template-columns: var(--sidebar-w) 1fr var(--phil-w);
  }
}

/* Mobile */
@media (max-width: 799px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr var(--bottom-nav-h);
  }
  .content {
    padding-bottom: calc(var(--bottom-nav-h) + 1rem);
  }
}

.backdrop {
  position: fixed; inset: 0; z-index: 199;
  background: rgba(0,0,0,.4);
}
```

**Step 3: Sidebar**

Create `frontend/src/components/Layout/Sidebar.tsx`:

```tsx
import { useStore } from '../../store/useStore'
import styles from './Sidebar.module.css'
import { api } from '../../api/client'

const NAV_ITEMS = [
  { view: 'dashboard' as const, label: 'Dashboard', icon: '⊞' },
  { view: 'mails' as const, label: 'Mails', icon: '✉' },
  { view: 'calendar' as const, label: 'Kalender', icon: '◫' },
  { view: 'tasks' as const, label: 'Aufgaben', icon: '✓' },
]

interface Props { onOpenPhil: () => void }

export function Sidebar({ onOpenPhil }: Props) {
  const { view, setView, user, setUser, mails } = useStore()
  const unread = mails.filter((m) => !m.is_read).length

  async function handleLogout() {
    await api.logout().catch(() => {})
    setUser(null)
  }

  return (
    <nav className={styles.sidebar}>
      <div className={styles.brand}>
        <span className={styles.brandName}>PHIL</span>
        <span className={styles.brandSub}>PIM Dashboard</span>
      </div>

      <div className={styles.nav}>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.view}
            className={`${styles.navItem} ${view === item.view ? styles.active : ''}`}
            onClick={() => setView(item.view)}
          >
            <span className={styles.navIcon}>{item.icon}</span>
            <span className={styles.navLabel}>{item.label}</span>
            {item.view === 'mails' && unread > 0 && (
              <span className={styles.badge}>{unread}</span>
            )}
          </button>
        ))}
      </div>

      <div className={styles.bottom}>
        <button className={styles.philBtn} onClick={onOpenPhil}>
          <img src="/phil.png" className={styles.philAvatar} alt="PHIL" />
          <span>Frag PHIL</span>
        </button>
        <div className={styles.userRow}>
          <span className={styles.userName}>{user?.username}</span>
          <button className={styles.logoutBtn} onClick={handleLogout} title="Abmelden">⏻</button>
        </div>
      </div>
    </nav>
  )
}
```

Create `frontend/src/components/Layout/Sidebar.module.css`:

```css
.sidebar {
  background: var(--sidebar-bg);
  color: var(--sidebar-text);
  display: flex; flex-direction: column;
  height: 100vh;
  overflow: hidden;
  border-right: 1px solid var(--sidebar-border);
  font-family: var(--font);
}

.brand {
  padding: 1.25rem 1.25rem .75rem;
  border-bottom: 1px solid var(--sidebar-border);
}
.brandName { display: block; color: var(--amber); font-weight: 700; font-size: var(--text-lg); }
.brandSub { display: block; font-size: var(--text-xs); color: #52525B; margin-top: 2px; }

.nav { flex: 1; padding: .75rem .5rem; display: flex; flex-direction: column; gap: 2px; }

.navItem {
  display: flex; align-items: center; gap: .75rem;
  padding: .6rem .75rem;
  border-radius: var(--radius-sm);
  color: var(--sidebar-text);
  font-size: var(--text-sm);
  font-family: var(--font);
  transition: background var(--transition), color var(--transition);
  position: relative;
}
.navItem:hover { background: var(--sidebar-hover); color: var(--sidebar-text-active); }
.navItem.active { background: var(--sidebar-active); color: var(--sidebar-text-active); }

.navIcon { font-size: 1rem; width: 1.25rem; text-align: center; flex-shrink: 0; }
.navLabel { flex: 1; }
.badge {
  background: var(--amber); color: white;
  border-radius: 999px; font-size: .65rem; font-weight: 600;
  padding: 1px 6px;
}

.bottom {
  padding: .75rem;
  border-top: 1px solid var(--sidebar-border);
  display: flex; flex-direction: column; gap: .5rem;
}

.philBtn {
  display: flex; align-items: center; gap: .6rem;
  padding: .6rem .75rem;
  background: var(--sidebar-active);
  border-radius: var(--radius-sm);
  color: var(--sidebar-text-active);
  font-size: var(--text-sm);
  font-family: var(--font);
  width: 100%;
  transition: background var(--transition);
}
.philBtn:hover { background: #52525B; }
.philAvatar { width: 24px; height: 24px; border-radius: 50%; object-fit: cover; }

.userRow {
  display: flex; align-items: center; justify-content: space-between;
  padding: .25rem .75rem;
}
.userName { font-size: var(--text-xs); color: #52525B; overflow: hidden; text-overflow: ellipsis; }
.logoutBtn { color: #52525B; font-size: 1rem; padding: .2rem; transition: color var(--transition); }
.logoutBtn:hover { color: #EF4444; }

/* Mobile: bottom nav strip */
@media (max-width: 799px) {
  .sidebar {
    flex-direction: row;
    height: var(--bottom-nav-h);
    position: fixed; bottom: 0; left: 0; right: 0;
    border-right: none; border-top: 1px solid var(--sidebar-border);
    z-index: 100;
  }
  .brand, .bottom { display: none; }
  .nav { flex-direction: row; padding: 0; gap: 0; }
  .navItem { flex: 1; flex-direction: column; gap: 2px; padding: .5rem .25rem;
    font-size: .6rem; border-radius: 0; justify-content: center; }
  .navIcon { font-size: 1.25rem; width: auto; }
  .badge { position: absolute; top: 4px; right: 12px; }
}
```

**Step 4: Update App.tsx**

```tsx
// frontend/src/App.tsx
import { useEffect } from 'react'
import { api } from './api/client'
import { useStore } from './store/useStore'
import { Login } from './components/Login/Login'
import { AppShell } from './components/Layout/AppShell'
import { Dashboard } from './components/Views/Dashboard'
import { MailsView } from './components/Views/MailsView'
import { CalendarView } from './components/Views/CalendarView'
import { TasksView } from './components/Views/TasksView'
import { useDataLoader } from './hooks/useDataLoader'
import type { User } from './api/types'

function ViewRouter() {
  const view = useStore((s) => s.view)
  if (view === 'dashboard') return <Dashboard />
  if (view === 'mails') return <MailsView />
  if (view === 'calendar') return <CalendarView />
  if (view === 'tasks') return <TasksView />
  return null
}

export default function App() {
  const { user, setUser } = useStore()
  const { loadAll } = useDataLoader()

  useEffect(() => {
    api.me().then((u) => {
      setUser(u)
      loadAll()
    }).catch(() => {})
  }, [])

  function handleLogin(u: User) {
    setUser(u)
    loadAll()
  }

  if (!user) return <Login onLogin={handleLogin} />

  return (
    <AppShell>
      <ViewRouter />
    </AppShell>
  )
}
```

**Step 5: Build + verify**

```bash
cd frontend && npm run build && cd ..
python -m pytest tests/ -v
```

Expected: 22 tests green, React login screen loads in browser.

**Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): Login screen + AppShell + Sidebar layout"
```

---

## Task 6: Dashboard + Mails view

**Files:**
- Create: `frontend/src/components/Views/Dashboard.tsx`
- Create: `frontend/src/components/Views/Dashboard.module.css`
- Create: `frontend/src/components/Views/MailsView.tsx`
- Create: `frontend/src/components/Views/MailsView.module.css`
- Create: `frontend/src/components/Cards/MailCard.tsx`
- Create: `frontend/src/components/Cards/MailCard.module.css`

**Step 1: Dashboard**

Create `frontend/src/components/Views/Dashboard.tsx`:

```tsx
import { useStore } from '../../store/useStore'
import type { Category } from '../../api/types'
import styles from './Dashboard.module.css'

const CATS: { cat: Category; label: string; colorClass: string }[] = [
  { cat: 'VIP', label: 'VIP', colorClass: 'vip' },
  { cat: 'Aktion nötig', label: 'Aktion', colorClass: 'aktion' },
  { cat: 'Nur Info', label: 'Info', colorClass: 'info' },
  { cat: 'Ignorieren', label: 'Ignorieren', colorClass: 'ignorieren' },
]

export function Dashboard() {
  const { mails, calendar, tasks, user, loadingMails, setView, setMailFilter } = useStore()

  const counts = CATS.reduce((acc, { cat }) => {
    acc[cat] = mails.filter((m) => m.kategorie === cat && m.triageStatus === 'done').length
    return acc
  }, {} as Record<Category, number>)

  const today = new Date().toISOString().slice(0, 10)
  const todayEvents = calendar.filter((e) => e.start?.slice(0, 10) === today)
  const urgentTasks = tasks.filter((t) => t.status !== 'Completed').slice(0, 5)

  function goToMails(cat: Category) {
    setMailFilter(cat)
    setView('mails')
  }

  return (
    <div className={styles.dashboard}>
      <header className={styles.header}>
        <h1 className={styles.greeting}>
          Guten {new Date().getHours() < 12 ? 'Morgen' : new Date().getHours() < 18 ? 'Tag' : 'Abend'},
          {' '}{user?.username.split('.')[0] || 'Prof'}!
        </h1>
        <p className={styles.date}>{new Date().toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' })}</p>
      </header>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Mails nach Kategorie</h2>
        <div className={styles.tileGrid}>
          {CATS.map(({ cat, label, colorClass }) => (
            <button
              key={cat}
              className={`${styles.tile} ${styles[colorClass]}`}
              onClick={() => goToMails(cat)}
            >
              <span className={styles.tileCount}>
                {loadingMails ? '…' : counts[cat]}
              </span>
              <span className={styles.tileLabel}>{label}</span>
            </button>
          ))}
        </div>
      </section>

      {todayEvents.length > 0 && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Heute</h2>
          <div className={styles.eventList}>
            {todayEvents.map((e) => (
              <div key={e.id} className={styles.eventItem}>
                <span className={styles.eventTime}>
                  {e.start ? new Date(e.start).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : ''}
                </span>
                <span className={styles.eventTitle}>{e.subject}</span>
                {e.location && <span className={styles.eventLoc}>📍 {e.location}</span>}
              </div>
            ))}
          </div>
        </section>
      )}

      {urgentTasks.length > 0 && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Offene Aufgaben</h2>
          <div className={styles.taskList}>
            {urgentTasks.map((t) => (
              <div key={t.id} className={styles.taskItem}>
                <span className={`${styles.taskPriority} ${styles[t.priority?.toLowerCase() || 'normal']}`} />
                <span className={styles.taskTitle}>{t.subject}</span>
                {t.due_date && (
                  <span className={styles.taskDue}>{t.due_date.slice(0, 10)}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {!user?.ews_connected && (
        <div className={styles.ewsNotice}>
          <span>⚠</span>
          <span>EWS nicht verbunden — Kalender und Aufgaben nicht verfügbar.</span>
        </div>
      )}
    </div>
  )
}
```

Create `frontend/src/components/Views/Dashboard.module.css`:

```css
.dashboard { padding: 2rem 2rem 1rem; max-width: 900px; }

.header { margin-bottom: 2rem; }
.greeting { font-size: var(--text-2xl); font-weight: 700; letter-spacing: -.02em; }
.date { color: #6B7280; font-size: var(--text-sm); margin-top: .25rem; }

.section { margin-bottom: 2rem; }
.sectionTitle { font-size: var(--text-sm); font-weight: 600; color: #6B7280; text-transform: uppercase; letter-spacing: .06em; margin-bottom: .75rem; }

.tileGrid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (min-width: 600px) { .tileGrid { grid-template-columns: repeat(4, 1fr); } }

.tile {
  display: flex; flex-direction: column; align-items: center; gap: .35rem;
  padding: 1.5rem 1rem; border-radius: var(--radius-lg);
  cursor: pointer; border: none; font-family: var(--font);
  transition: transform var(--transition), box-shadow var(--transition);
}
.tile:hover { transform: translateY(-2px); box-shadow: var(--card-shadow-hover); }
.tileCount { font-size: 2.75rem; font-weight: 700; line-height: 1; }
.tileLabel { font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: .05em; opacity: .8; }

.vip { background: var(--vip-bg); color: var(--vip-text); }
.aktion { background: var(--aktion-bg); color: var(--aktion-text); }
.info { background: var(--info-bg); color: var(--info-text); }
.ignorieren { background: var(--ignorieren-bg); color: var(--ignorieren-text); }

.eventList { display: flex; flex-direction: column; gap: 8px; }
.eventItem {
  display: flex; align-items: baseline; gap: .75rem;
  padding: .75rem 1rem;
  background: var(--card-bg); border-radius: var(--radius); border: 1px solid var(--card-border);
  box-shadow: var(--card-shadow);
}
.eventTime { font-size: var(--text-sm); font-weight: 600; color: var(--amber); flex-shrink: 0; }
.eventTitle { font-size: var(--text-base); flex: 1; }
.eventLoc { font-size: var(--text-xs); color: #6B7280; }

.taskList { display: flex; flex-direction: column; gap: 8px; }
.taskItem {
  display: flex; align-items: center; gap: .75rem;
  padding: .65rem 1rem;
  background: var(--card-bg); border-radius: var(--radius); border: 1px solid var(--card-border);
  box-shadow: var(--card-shadow);
}
.taskPriority { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.high { background: var(--vip-badge); }
.normal { background: var(--info-badge); }
.low { background: var(--ignorieren-badge); }
.taskTitle { flex: 1; font-size: var(--text-sm); }
.taskDue { font-size: var(--text-xs); color: #6B7280; }

.ewsNotice {
  display: flex; align-items: center; gap: .5rem;
  padding: .75rem 1rem; border-radius: var(--radius);
  background: var(--aktion-bg); color: var(--aktion-text);
  font-size: var(--text-sm); border: 1px solid #FDE68A;
}
```

**Step 2: MailCard component**

Create `frontend/src/components/Cards/MailCard.tsx`:

```tsx
import { useStore } from '../../store/useStore'
import type { TriagedMail } from '../../api/types'
import styles from './MailCard.module.css'

const CAT_COLORS: Record<string, string> = {
  'VIP': 'vip',
  'Aktion nötig': 'aktion',
  'Nur Info': 'info',
  'Ignorieren': 'ignorieren',
}

interface Props { mail: TriagedMail }

export function MailCard({ mail }: Props) {
  const { selection, setSelection } = useStore()
  const isSelected = selection?.type === 'mail' && selection.item.id === mail.id
  const colorClass = CAT_COLORS[mail.kategorie] ?? 'info'

  return (
    <div
      className={`${styles.card} ${isSelected ? styles.selected : ''}`}
      onClick={() => setSelection({ type: 'mail', item: mail })}
    >
      <div className={styles.header}>
        <span className={`${styles.badge} ${styles[colorClass]}`}>{mail.kategorie}</span>
        {mail.triageStatus === 'pending' && <span className={styles.spinner}>⟳</span>}
        <span className={styles.date}>
          {mail.datetime_received
            ? new Date(mail.datetime_received).toLocaleDateString('de-DE', { day: '2-digit', month: 'short' })
            : ''}
        </span>
      </div>
      <p className={styles.subject}>{mail.subject}</p>
      <p className={styles.sender}>{mail.sender}</p>
      {mail.zusammenfassung && (
        <p className={styles.summary}>{mail.zusammenfassung}</p>
      )}
    </div>
  )
}
```

Create `frontend/src/components/Cards/MailCard.module.css`:

```css
.card {
  background: var(--card-bg);
  border: 1.5px solid var(--card-border);
  border-radius: var(--radius);
  padding: 1rem 1.125rem;
  cursor: pointer;
  transition: box-shadow var(--transition), border-color var(--transition), transform var(--transition);
  font-family: var(--font);
}
.card:hover { box-shadow: var(--card-shadow-hover); transform: translateY(-1px); }
.card.selected { border-color: var(--amber); box-shadow: 0 0 0 2px rgba(245,158,11,.2); }

.header { display: flex; align-items: center; gap: .5rem; margin-bottom: .5rem; }
.badge {
  font-size: var(--text-xs); font-weight: 600; text-transform: uppercase;
  letter-spacing: .04em; padding: 2px 8px; border-radius: 999px;
}
.vip { background: var(--vip-bg); color: var(--vip-text); }
.aktion { background: var(--aktion-bg); color: var(--aktion-text); }
.info { background: var(--info-bg); color: var(--info-text); }
.ignorieren { background: var(--ignorieren-bg); color: var(--ignorieren-text); }

.spinner { color: #9CA3AF; font-size: 1rem; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.date { margin-left: auto; font-size: var(--text-xs); color: #9CA3AF; }

.subject { font-size: var(--text-base); font-weight: 600; margin-bottom: .2rem; line-height: 1.35; }
.sender { font-size: var(--text-sm); color: #6B7280; margin-bottom: .4rem; }
.summary { font-size: var(--text-sm); color: #374151; line-height: 1.5; }
```

**Step 3: MailsView**

Create `frontend/src/components/Views/MailsView.tsx`:

```tsx
import { useStore } from '../../store/useStore'
import { MailCard } from '../Cards/MailCard'
import styles from './MailsView.module.css'
import type { Category } from '../../api/types'

const FILTERS: Array<{ value: Category | 'all'; label: string }> = [
  { value: 'all', label: 'Alle' },
  { value: 'VIP', label: 'VIP' },
  { value: 'Aktion nötig', label: 'Aktion' },
  { value: 'Nur Info', label: 'Info' },
  { value: 'Ignorieren', label: 'Ignorieren' },
]

export function MailsView() {
  const { mails, mailFilter, setMailFilter, loadingMails } = useStore()

  const filtered = mailFilter === 'all'
    ? mails
    : mails.filter((m) => m.kategorie === mailFilter)

  const sorted = [...filtered].sort((a, b) => {
    if (a.triageStatus === 'pending' && b.triageStatus !== 'pending') return 1
    if (b.triageStatus === 'pending' && a.triageStatus !== 'pending') return -1
    return (a.priorität ?? 9) - (b.priorität ?? 9)
  })

  return (
    <div className={styles.view}>
      <header className={styles.header}>
        <h1 className={styles.title}>Mails</h1>
        {loadingMails && <span className={styles.loading}>Lade…</span>}
      </header>

      <div className={styles.filters}>
        {FILTERS.map(({ value, label }) => (
          <button
            key={value}
            className={`${styles.pill} ${mailFilter === value ? styles.active : ''}`}
            onClick={() => setMailFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className={styles.list}>
        {sorted.length === 0 ? (
          <p className={styles.empty}>{loadingMails ? 'Lade Mails…' : 'Keine Mails.'}</p>
        ) : (
          sorted.map((mail) => <MailCard key={mail.id} mail={mail} />)
        )}
      </div>
    </div>
  )
}
```

Create `frontend/src/components/Views/MailsView.module.css`:

```css
.view { padding: 1.5rem 2rem; max-width: 780px; }
.header { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
.title { font-size: var(--text-xl); font-weight: 700; }
.loading { color: #9CA3AF; font-size: var(--text-sm); }

.filters { display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
.pill {
  padding: .35rem .9rem; border-radius: 999px;
  font-size: var(--text-sm); font-family: var(--font);
  border: 1.5px solid var(--content-border);
  background: var(--card-bg); color: #374151;
  transition: all var(--transition);
}
.pill:hover { border-color: var(--amber); color: var(--amber-dark); }
.pill.active { background: var(--amber); border-color: var(--amber); color: white; font-weight: 600; }

.list { display: flex; flex-direction: column; gap: 10px; }
.empty { color: #6B7280; font-size: var(--text-sm); padding: 2rem 0; text-align: center; }
```

**Step 4: Build + verify**

```bash
cd frontend && npm run build && cd ..
python -m pytest tests/ -v
```

Expected: 22 tests green.

**Step 5: Commit**

```bash
git add frontend/src/components/
git commit -m "feat(frontend): Dashboard tiles, MailsView with filter pills, MailCard"
```

---

## Task 7: Calendar + Tasks views

**Files:**
- Create: `frontend/src/components/Views/CalendarView.tsx`
- Create: `frontend/src/components/Views/CalendarView.module.css`
- Create: `frontend/src/components/Views/TasksView.tsx`
- Create: `frontend/src/components/Views/TasksView.module.css`

**Step 1: CalendarView**

Create `frontend/src/components/Views/CalendarView.tsx`:

```tsx
import { useState } from 'react'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import styles from './CalendarView.module.css'

export function CalendarView() {
  const { calendar, setCalendar, user, setSelection, selection } = useStore()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ subject: '', start: '', end: '', location: '' })
  const [saving, setSaving] = useState(false)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.createCalendar(form.subject, form.start, form.end, form.location)
      const { items } = await api.calendar()
      setCalendar(items)
      setShowForm(false)
      setForm({ subject: '', start: '', end: '', location: '' })
    } catch (err) { console.error(err) }
    finally { setSaving(false) }
  }

  const grouped = calendar.reduce((acc, item) => {
    const day = item.start?.slice(0, 10) ?? 'unbekannt'
    acc[day] = acc[day] ?? []
    acc[day].push(item)
    return acc
  }, {} as Record<string, typeof calendar>)

  const days = Object.keys(grouped).sort()

  return (
    <div className={styles.view}>
      <header className={styles.header}>
        <h1 className={styles.title}>Kalender</h1>
        {user?.ews_connected && (
          <button className={styles.addBtn} onClick={() => setShowForm(!showForm)}>+ Neu</button>
        )}
      </header>

      {!user?.ews_connected && (
        <p className={styles.noEws}>EWS nicht verbunden — Kalender nicht verfügbar.</p>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className={styles.form}>
          <input className={styles.input} placeholder="Titel" value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })} required />
          <div className={styles.row}>
            <input className={styles.input} type="datetime-local" value={form.start}
              onChange={(e) => setForm({ ...form, start: e.target.value })} required />
            <input className={styles.input} type="datetime-local" value={form.end}
              onChange={(e) => setForm({ ...form, end: e.target.value })} required />
          </div>
          <input className={styles.input} placeholder="Ort (optional)" value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })} />
          <div className={styles.formActions}>
            <button type="button" className={styles.cancelBtn} onClick={() => setShowForm(false)}>Abbrechen</button>
            <button type="submit" className={styles.saveBtn} disabled={saving}>{saving ? '…' : 'Speichern'}</button>
          </div>
        </form>
      )}

      <div className={styles.agenda}>
        {days.length === 0 && user?.ews_connected && (
          <p className={styles.empty}>Keine Termine in den nächsten 14 Tagen.</p>
        )}
        {days.map((day) => (
          <div key={day} className={styles.dayGroup}>
            <h3 className={styles.dayLabel}>
              {new Date(day + 'T00:00:00').toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' })}
            </h3>
            {grouped[day].map((item) => {
              const isSelected = selection?.type === 'calendar' && selection.item.id === item.id
              return (
                <div
                  key={item.id}
                  className={`${styles.event} ${isSelected ? styles.selected : ''}`}
                  onClick={() => setSelection({ type: 'calendar', item })}
                >
                  <div className={styles.timeBar} />
                  <div className={styles.eventContent}>
                    <p className={styles.eventTime}>
                      {item.start ? new Date(item.start).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : ''} –
                      {item.end ? new Date(item.end).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : ''}
                    </p>
                    <p className={styles.eventTitle}>{item.subject}</p>
                    {item.location && <p className={styles.eventLoc}>📍 {item.location}</p>}
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
```

Create `frontend/src/components/Views/CalendarView.module.css`:

```css
.view { padding: 1.5rem 2rem; max-width: 780px; }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem; }
.title { font-size: var(--text-xl); font-weight: 700; }
.addBtn {
  padding: .45rem 1rem; background: var(--amber); color: white;
  border-radius: var(--radius-sm); font-size: var(--text-sm); font-weight: 600; font-family: var(--font);
  transition: background var(--transition);
}
.addBtn:hover { background: var(--amber-dark); }
.noEws { color: var(--aktion-text); font-size: var(--text-sm); background: var(--aktion-bg); padding: .75rem 1rem; border-radius: var(--radius); border: 1px solid #FDE68A; }

.form { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius-lg); padding: 1.25rem; margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: .75rem; box-shadow: var(--card-shadow); }
.input { padding: .65rem .9rem; border: 1.5px solid var(--content-border); border-radius: var(--radius-sm); font-family: var(--font); font-size: var(--text-sm); background: var(--content-bg); width: 100%; }
.input:focus { border-color: var(--amber); outline: none; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; }
.formActions { display: flex; justify-content: flex-end; gap: .5rem; }
.cancelBtn { padding: .45rem .9rem; border-radius: var(--radius-sm); font-size: var(--text-sm); font-family: var(--font); color: #6B7280; }
.cancelBtn:hover { background: var(--content-border); }
.saveBtn { padding: .45rem 1rem; background: var(--amber); color: white; border-radius: var(--radius-sm); font-size: var(--text-sm); font-weight: 600; font-family: var(--font); }
.saveBtn:disabled { opacity: .6; }

.agenda { display: flex; flex-direction: column; gap: 1.5rem; }
.empty { color: #6B7280; text-align: center; padding: 2rem; font-size: var(--text-sm); }
.dayLabel { font-size: var(--text-sm); font-weight: 600; color: #6B7280; text-transform: uppercase; letter-spacing: .05em; margin-bottom: .5rem; }
.dayGroup { display: flex; flex-direction: column; gap: 8px; }

.event {
  display: flex; align-items: stretch;
  background: var(--card-bg); border-radius: var(--radius); border: 1.5px solid var(--card-border);
  box-shadow: var(--card-shadow); overflow: hidden; cursor: pointer;
  transition: box-shadow var(--transition), border-color var(--transition);
}
.event:hover { box-shadow: var(--card-shadow-hover); }
.event.selected { border-color: var(--amber); box-shadow: 0 0 0 2px rgba(245,158,11,.2); }
.timeBar { width: 4px; background: var(--amber); flex-shrink: 0; }
.eventContent { padding: .75rem 1rem; }
.eventTime { font-size: var(--text-xs); color: var(--amber); font-weight: 600; margin-bottom: .25rem; }
.eventTitle { font-size: var(--text-base); font-weight: 500; }
.eventLoc { font-size: var(--text-xs); color: #6B7280; margin-top: .2rem; }
```

**Step 2: TasksView**

Create `frontend/src/components/Views/TasksView.tsx`:

```tsx
import { useState } from 'react'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import styles from './TasksView.module.css'

const PRIORITY_COLORS: Record<string, string> = {
  High: 'high', Normal: 'normal', Low: 'low',
}

export function TasksView() {
  const { tasks, setTasks, removeTask, user, setSelection, selection } = useStore()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ subject: '', due_date: '', body: '', priority: 'Normal' })
  const [saving, setSaving] = useState(false)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.createTask(form.subject, form.due_date || undefined, form.body, form.priority)
      const { tasks: fresh } = await api.tasks()
      setTasks(fresh)
      setShowForm(false)
      setForm({ subject: '', due_date: '', body: '', priority: 'Normal' })
    } catch (err) { console.error(err) }
    finally { setSaving(false) }
  }

  async function handleComplete(id: string, changekey: string) {
    try {
      await api.completeTask(id, changekey)
      removeTask(id)
    } catch (err) { console.error(err) }
  }

  const sorted = [...tasks].sort((a, b) => {
    const prio = { High: 0, Normal: 1, Low: 2 }
    return (prio[a.priority as keyof typeof prio] ?? 1) - (prio[b.priority as keyof typeof prio] ?? 1)
  })

  return (
    <div className={styles.view}>
      <header className={styles.header}>
        <h1 className={styles.title}>Aufgaben</h1>
        {user?.ews_connected && (
          <button className={styles.addBtn} onClick={() => setShowForm(!showForm)}>+ Neu</button>
        )}
      </header>

      {!user?.ews_connected && (
        <p className={styles.noEws}>EWS nicht verbunden — Aufgaben nicht verfügbar.</p>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className={styles.form}>
          <input className={styles.input} placeholder="Titel" value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })} required />
          <div className={styles.row}>
            <input className={styles.input} type="date" value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            <select className={styles.input} value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              <option value="High">Hoch</option>
              <option value="Normal">Normal</option>
              <option value="Low">Niedrig</option>
            </select>
          </div>
          <textarea className={styles.textarea} placeholder="Notizen…" value={form.body}
            onChange={(e) => setForm({ ...form, body: e.target.value })} rows={3} />
          <div className={styles.formActions}>
            <button type="button" className={styles.cancelBtn} onClick={() => setShowForm(false)}>Abbrechen</button>
            <button type="submit" className={styles.saveBtn} disabled={saving}>{saving ? '…' : 'Speichern'}</button>
          </div>
        </form>
      )}

      <div className={styles.list}>
        {sorted.length === 0 && user?.ews_connected && (
          <p className={styles.empty}>Keine offenen Aufgaben.</p>
        )}
        {sorted.map((task) => {
          const isSelected = selection?.type === 'task' && selection.item.id === task.id
          return (
            <div
              key={task.id}
              className={`${styles.task} ${isSelected ? styles.selected : ''}`}
              onClick={() => setSelection({ type: 'task', item: task })}
            >
              <button
                className={styles.checkbox}
                onClick={(e) => { e.stopPropagation(); handleComplete(task.id, task.changekey) }}
                title="Als erledigt markieren"
              >○</button>
              <div className={styles.taskContent}>
                <p className={styles.taskTitle}>{task.subject}</p>
                {task.due_date && (
                  <p className={styles.taskDue}>Fällig: {task.due_date.slice(0, 10)}</p>
                )}
              </div>
              <span className={`${styles.prioBadge} ${styles[PRIORITY_COLORS[task.priority] ?? 'normal']}`}>
                {task.priority}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

Create `frontend/src/components/Views/TasksView.module.css`:

```css
.view { padding: 1.5rem 2rem; max-width: 780px; }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem; }
.title { font-size: var(--text-xl); font-weight: 700; }
.addBtn { padding: .45rem 1rem; background: var(--amber); color: white; border-radius: var(--radius-sm); font-size: var(--text-sm); font-weight: 600; font-family: var(--font); transition: background var(--transition); }
.addBtn:hover { background: var(--amber-dark); }
.noEws { color: var(--aktion-text); font-size: var(--text-sm); background: var(--aktion-bg); padding: .75rem 1rem; border-radius: var(--radius); border: 1px solid #FDE68A; }

.form { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius-lg); padding: 1.25rem; margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: .75rem; box-shadow: var(--card-shadow); }
.input { padding: .65rem .9rem; border: 1.5px solid var(--content-border); border-radius: var(--radius-sm); font-family: var(--font); font-size: var(--text-sm); background: var(--content-bg); width: 100%; }
.input:focus { border-color: var(--amber); outline: none; }
.textarea { padding: .65rem .9rem; border: 1.5px solid var(--content-border); border-radius: var(--radius-sm); font-family: var(--font); font-size: var(--text-sm); background: var(--content-bg); width: 100%; resize: vertical; }
.textarea:focus { border-color: var(--amber); outline: none; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; }
.formActions { display: flex; justify-content: flex-end; gap: .5rem; }
.cancelBtn { padding: .45rem .9rem; border-radius: var(--radius-sm); font-size: var(--text-sm); font-family: var(--font); color: #6B7280; }
.cancelBtn:hover { background: var(--content-border); }
.saveBtn { padding: .45rem 1rem; background: var(--amber); color: white; border-radius: var(--radius-sm); font-size: var(--text-sm); font-weight: 600; font-family: var(--font); }
.saveBtn:disabled { opacity: .6; }

.list { display: flex; flex-direction: column; gap: 8px; }
.empty { color: #6B7280; text-align: center; padding: 2rem; font-size: var(--text-sm); }

.task {
  display: flex; align-items: center; gap: .75rem;
  background: var(--card-bg); border: 1.5px solid var(--card-border); border-radius: var(--radius);
  padding: .75rem 1rem; cursor: pointer;
  transition: box-shadow var(--transition), border-color var(--transition);
  box-shadow: var(--card-shadow);
}
.task:hover { box-shadow: var(--card-shadow-hover); }
.task.selected { border-color: var(--amber); box-shadow: 0 0 0 2px rgba(245,158,11,.2); }

.checkbox { font-size: 1.25rem; color: #D1D5DB; flex-shrink: 0; transition: color var(--transition); }
.checkbox:hover { color: var(--amber); }
.taskContent { flex: 1; }
.taskTitle { font-size: var(--text-base); font-weight: 500; }
.taskDue { font-size: var(--text-xs); color: #6B7280; margin-top: .15rem; }
.prioBadge { font-size: var(--text-xs); font-weight: 600; padding: 2px 8px; border-radius: 999px; }
.high { background: var(--vip-bg); color: var(--vip-text); }
.normal { background: var(--info-bg); color: var(--info-text); }
.low { background: var(--ignorieren-bg); color: var(--ignorieren-text); }
```

**Step 3: Build + verify**

```bash
cd frontend && npm run build && cd ..
python -m pytest tests/ -v
```

Expected: 22 tests green.

**Step 4: Commit**

```bash
git add frontend/src/components/Views/
git commit -m "feat(frontend): CalendarView + TasksView with create/complete actions"
```

---

## Task 8: PHIL Panel (persistent, context-sensitive)

**Files:**
- Create: `frontend/src/components/Phil/PhilPanel.tsx`
- Create: `frontend/src/components/Phil/PhilPanel.module.css`

**Step 1: PhilPanel component**

Create `frontend/src/components/Phil/PhilPanel.tsx`:

```tsx
import { useState, useRef, useEffect } from 'react'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import styles from './PhilPanel.module.css'

interface ChatMessage { role: 'user' | 'phil'; text: string }

interface Props { open: boolean; onClose: () => void }

export function PhilPanel({ open, onClose }: Props) {
  const { selection, mails, calendar, tasks } = useStore()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [philAudio, setPhilAudio] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Context label for selected item
  const contextLabel = selection
    ? selection.type === 'mail'
      ? `Mail: "${selection.item.subject.slice(0, 50)}"`
      : selection.type === 'calendar'
      ? `Termin: "${selection.item.subject.slice(0, 50)}"`
      : `Aufgabe: "${selection.item.subject.slice(0, 50)}"`
    : null

  // Context-sensitive quick actions
  const quickActions: string[] = selection?.type === 'mail'
    ? ['Zusammenfassen', 'Antwort formulieren', 'Priorität begründen']
    : selection?.type === 'calendar'
    ? ['Vorbereitung checken', 'Agenda vorschlagen', 'Konflikt prüfen']
    : selection?.type === 'task'
    ? ['Aufgabe beschreiben', 'Aufwand schätzen', 'Unteraufgaben']
    : ['Was steht heute an?', 'Wichtigste Aufgaben', 'Freie Slots finden']

  async function send(text: string) {
    if (!text.trim() || streaming) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text }])
    setStreaming(true)

    // Build context message
    let contextMsg = text
    if (selection?.type === 'mail') {
      const m = selection.item
      contextMsg = `[Kontext: Mail von ${m.sender}, Betreff: "${m.subject}"]\n\n${m.zusammenfassung ? 'Zusammenfassung: ' + m.zusammenfassung + '\n\n' : ''}${text}`
    } else if (selection?.type === 'calendar') {
      const c = selection.item
      contextMsg = `[Kontext: Termin "${c.subject}" am ${c.start?.slice(0, 10) ?? '?'}]\n\n${text}`
    } else if (selection?.type === 'task') {
      const t = selection.item
      contextMsg = `[Kontext: Aufgabe "${t.subject}", Priorität: ${t.priority}, Fällig: ${t.due_date ?? 'unbekannt'}]\n\n${text}`
    }

    let philText = ''
    setMessages((prev) => [...prev, { role: 'phil', text: '' }])

    try {
      const stream = api.chatStream(contextMsg, true)
      const reader = stream.getReader()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        philText += value
        setMessages((prev) => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'phil', text: philText }
          return updated
        })
      }
    } catch (e) {
      console.error(e)
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = { role: 'phil', text: 'Fehler bei der Verbindung.' }
        return updated
      })
    } finally {
      setStreaming(false)
    }

    // TTS for PHIL response
    if (philText) {
      try {
        const url = await api.tts(philText.slice(0, 300))
        const prev = philAudio
        setPhilAudio(url)
        const audio = new Audio(url)
        audio.play()
        if (prev) URL.revokeObjectURL(prev)
      } catch { /* TTS optional */ }
    }
  }

  return (
    <div className={`${styles.panel} ${open ? styles.open : ''}`}>
      <div className={styles.header}>
        <img src="/phil.png" className={styles.avatar} alt="PHIL" />
        <div className={styles.headerText}>
          <span className={styles.headerTitle}>PHIL</span>
          {contextLabel && <span className={styles.contextLabel}>{contextLabel}</span>}
        </div>
        <button className={styles.closeBtn} onClick={onClose}>✕</button>
      </div>

      {contextLabel && (
        <div className={styles.quickActions}>
          {quickActions.map((action) => (
            <button key={action} className={styles.quickBtn} onClick={() => send(action)}>
              {action}
            </button>
          ))}
        </div>
      )}

      {!contextLabel && messages.length === 0 && (
        <div className={styles.quickActions}>
          {quickActions.map((action) => (
            <button key={action} className={styles.quickBtn} onClick={() => send(action)}>
              {action}
            </button>
          ))}
        </div>
      )}

      <div className={styles.messages}>
        {messages.length === 0 && (
          <p className={styles.emptyMsg}>
            {selection
              ? `Ich sehe den ausgewählten ${selection.type === 'mail' ? 'Mail' : selection.type === 'calendar' ? 'Termin' : 'Aufgabe'}. Was möchtest du wissen?`
              : 'Hallo! Wähle ein Element aus oder stelle mir eine Frage.'}
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`${styles.msg} ${styles[msg.role]}`}>
            {msg.role === 'phil' && (
              <img src="/phil.png" className={styles.msgAvatar} alt="PHIL" />
            )}
            <div className={styles.msgBubble}>
              {msg.text || (streaming && i === messages.length - 1 ? '…' : '')}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className={styles.inputRow}>
        <input
          className={styles.input}
          placeholder="Frag PHIL…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
          disabled={streaming}
        />
        <button
          className={styles.sendBtn}
          onClick={() => send(input)}
          disabled={!input.trim() || streaming}
        >→</button>
      </div>
    </div>
  )
}
```

Create `frontend/src/components/Phil/PhilPanel.module.css`:

```css
.panel {
  background: var(--phil-bg);
  border-left: 1px solid var(--phil-border);
  display: flex; flex-direction: column;
  height: 100vh;
  overflow: hidden;
  font-family: var(--font);
  transform: translateX(100%);
  transition: transform .3s cubic-bezier(.4,0,.2,1);
  z-index: 200;
}

/* Desktop: side panel */
@media (min-width: 800px) {
  .panel { position: static; transform: none; width: var(--phil-w); display: none; }
  .panel.open { display: flex; }
}

/* Mobile: slide-up sheet */
@media (max-width: 799px) {
  .panel {
    position: fixed; bottom: var(--bottom-nav-h); left: 0; right: 0;
    height: 72vh; border-left: none; border-top: 1px solid var(--phil-border);
    border-radius: 16px 16px 0 0;
    transform: translateY(100%);
  }
  .panel.open { transform: translateY(0); }
}

.header {
  display: flex; align-items: center; gap: .75rem;
  padding: 1rem 1.125rem .75rem;
  border-bottom: 1px solid var(--phil-border);
  flex-shrink: 0;
}
.avatar { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; border: 2px solid var(--amber); }
.headerText { flex: 1; }
.headerTitle { display: block; font-weight: 700; font-size: var(--text-base); }
.contextLabel {
  display: block; font-size: var(--text-xs); color: var(--amber);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 240px;
}
.closeBtn { color: #9CA3AF; font-size: 1rem; padding: .25rem; transition: color var(--transition); }
.closeBtn:hover { color: #374151; }

.quickActions {
  padding: .75rem 1rem .5rem;
  display: flex; flex-wrap: wrap; gap: .4rem;
  border-bottom: 1px solid var(--phil-border);
  flex-shrink: 0;
}
.quickBtn {
  padding: .3rem .7rem;
  border: 1.5px solid var(--content-border); border-radius: 999px;
  font-size: var(--text-xs); font-family: var(--font); color: #374151;
  background: var(--content-bg);
  transition: all var(--transition); white-space: nowrap;
}
.quickBtn:hover { border-color: var(--amber); color: var(--amber-dark); background: var(--amber-light); }

.messages { flex: 1; overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: .75rem; }
.emptyMsg { color: #9CA3AF; font-size: var(--text-sm); text-align: center; padding: 1rem 0; line-height: 1.6; }

.msg { display: flex; align-items: flex-end; gap: .5rem; }
.msg.user { flex-direction: row-reverse; }
.msgAvatar { width: 28px; height: 28px; border-radius: 50%; object-fit: cover; flex-shrink: 0; }
.msgBubble {
  max-width: 85%; padding: .65rem .9rem;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm); line-height: 1.55;
  white-space: pre-wrap;
}
.phil .msgBubble { background: var(--content-bg); color: #18181B; border-bottom-left-radius: 4px; }
.user .msgBubble { background: var(--amber); color: white; border-bottom-right-radius: 4px; }

.inputRow {
  display: flex; gap: .5rem;
  padding: .75rem 1rem;
  border-top: 1px solid var(--phil-border);
  flex-shrink: 0;
}
.input {
  flex: 1; padding: .65rem .9rem;
  border: 1.5px solid var(--content-border); border-radius: var(--radius);
  font-family: var(--font); font-size: var(--text-sm);
  transition: border-color var(--transition);
}
.input:focus { border-color: var(--amber); }
.input:disabled { opacity: .6; }
.sendBtn {
  padding: .65rem .9rem; background: var(--amber); color: white;
  border-radius: var(--radius); font-size: 1rem; font-weight: 700;
  transition: background var(--transition);
}
.sendBtn:hover:not(:disabled) { background: var(--amber-dark); }
.sendBtn:disabled { opacity: .5; cursor: not-allowed; }
```

**Step 2: Update AppShell to pass phil state and use 3-column layout**

Update `frontend/src/components/Layout/AppShell.tsx`:

```tsx
import { useState } from 'react'
import { useStore } from '../../store/useStore'
import { Sidebar } from './Sidebar'
import { PhilPanel } from '../Phil/PhilPanel'
import styles from './AppShell.module.css'

interface Props { children: React.ReactNode }

export function AppShell({ children }: Props) {
  const [philOpen, setPhilOpen] = useState(true)  // open by default on desktop

  return (
    <div className={styles.shell} data-phil-open={philOpen ? 'true' : 'false'}>
      <Sidebar onOpenPhil={() => setPhilOpen(true)} />
      <main className={styles.content}>{children}</main>
      <PhilPanel open={philOpen} onClose={() => setPhilOpen(false)} />
      {/* Mobile backdrop */}
      {philOpen && (
        <div className={`${styles.backdrop} ${styles.mobileOnly}`} onClick={() => setPhilOpen(false)} />
      )}
    </div>
  )
}
```

Update `AppShell.module.css` to handle 3-column:

```css
.shell {
  display: grid;
  grid-template-columns: var(--sidebar-w) 1fr;
  height: 100vh;
  overflow: hidden;
}

/* 3-column when PHIL panel open on desktop */
@media (min-width: 800px) {
  .shell[data-phil-open="true"] {
    grid-template-columns: var(--sidebar-w) 1fr var(--phil-w);
  }
}

.content {
  overflow-y: auto;
  background: var(--content-bg);
  min-height: 100vh;
}

/* Mobile */
@media (max-width: 799px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr;
    padding-bottom: var(--bottom-nav-h);
  }
}

.backdrop {
  position: fixed; inset: 0; z-index: 199;
  background: rgba(0,0,0,.4);
}

.mobileOnly {
  display: none;
}
@media (max-width: 799px) {
  .mobileOnly { display: block; }
}
```

**Step 3: Build + verify**

```bash
cd frontend && npm run build && cd ..
python -m pytest tests/ -v
```

Expected: 22 tests green, 3-column layout works, PHIL panel context-sensitive.

**Step 4: Commit**

```bash
git add frontend/src/components/Phil/ frontend/src/components/Layout/
git commit -m "feat(frontend): persistent PHIL panel, context-sensitive quick actions"
```

---

## Task 9: Dockerfile update + copy phil.png to static

**Files:**
- Modify: `webapp/Dockerfile`
- Modify: `webapp/docker-compose.yml`

**Step 1: Update Dockerfile with Node build stage**

```dockerfile
# Stage 1 — Node build
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# Output: /app/frontend/../static = /app/static

# Stage 2 — Python runtime
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/static ./static/

# Copy phil.png to static (for browser)
COPY frontend/public/phil.png ./static/

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Update docker-compose.yml**

Change domain from `kn-triage.butscher.cloud` to `kn-mail.butscher.cloud` and service/image name from `uc2-triage` to `kn-mail`.

**Step 3: Copy phil.png to frontend/public/**

```bash
cp frontend/phil.png frontend/public/phil.png 2>/dev/null || true
```

(The `phil.png` is currently in `frontend/` — Vite serves `public/` at root, so `phil.png` in `public/` becomes `/phil.png` in the browser.)

**Step 4: Verify build**

```bash
cd frontend && npm run build && cd ..
python -m pytest tests/ -v
```

Expected: `static/phil.png` copied, 22 tests green.

**Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml frontend/public/
git commit -m "feat(docker): Node build stage + kn-mail.butscher.cloud domain"
```

---

## Verification

After all tasks complete:

```bash
# 1. Run all tests
cd UC2_Nachrichten_Triage/webapp
python -m pytest tests/ -v
# Expected: 22+ tests, all green

# 2. Start backend
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8001

# 3. Start Vite dev server (separate terminal)
cd frontend && npm run dev
# Browser: http://localhost:5173 → Login screen with dark background

# 4. Login with THWS credentials → Dashboard with 4 category tiles
# 5. Click a tile → MailsView filtered
# 6. Click a mail card → PHIL panel shows context + quick actions
# 7. Type message or click quick action → Phil responds (streamed)
# 8. Navigate to Kalender/Aufgaben → data loads if EWS connected
# 9. Settings/Logout in sidebar bottom

# 10. Production build test
cd frontend && npm run build
curl http://localhost:8001/ -L  # Returns React index.html

# 11. Mobile: Chrome DevTools → iPhone 15 viewport
# Expected: bottom nav, PHIL as slide-up sheet
```
