import type { User, TriagedMail, CalendarItem, Task, TrainStation, TrainJourney, KnowledgeResult, OntologyEntities, LLMMode, MemoryFact, MemoryStats } from './types'

/** Feuert ein CustomEvent wenn der Server 401 zurückgibt — App.tsx hört darauf und zeigt Login. */
function _handle401(status: number) {
  if (status === 401) window.dispatchEvent(new CustomEvent('session-expired'))
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    _handle401(r.status)
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw Object.assign(new Error(err.detail ?? r.statusText), { status: r.status, data: err })
  }
  return r.json()
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    _handle401(r.status)
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw Object.assign(new Error(err.detail ?? r.statusText), { status: r.status, data: err })
  }
  return r.json()
}

async function del<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    _handle401(r.status)
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw Object.assign(new Error(err.detail ?? r.statusText), { status: r.status, data: err })
  }
  return r.json()
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw Object.assign(new Error(err.detail ?? r.statusText), { status: r.status, data: err })
  }
  return r.json()
}

export const api = {
  // Auth
  me: () => get<User>('/api/auth/me'),
  login: (username: string, password: string, institution: string, exchange_email?: string, llm_mode: LLMMode = 'cloud') =>
    post<User & { status: string }>('/api/auth/login', { username, password, institution, exchange_email, llm_mode }),

  // LLM Health
  llmHealth: (mode: LLMMode = 'local') =>
    get<{ status: string; provider: string; endpoint?: string; model?: string; error?: string }>(
      `/api/health/llm?mode=${mode}`
    ),
  logout: () => post<{ status: string }>('/api/auth/logout', {}),

  // Mails
  fetchMails: (max_count = 30, unread_only = false) =>
    post<{ emails: Array<Omit<TriagedMail, 'kategorie' | 'priorität' | 'zusammenfassung' | 'empfohlene_aktion' | 'id' | 'triageStatus'>> }>(
      '/api/exchange/fetch', { max_count, unread_only }),

  // Triage
  analyze: (email_text: string, meta?: { mail_id: string; subject: string; sender: string; date: string }) =>
    post<{ kategorie: string; priorität: number; zusammenfassung: string; empfohlene_aktion: string; stimmung?: number }>(
      '/api/analyze', { email_text, ...meta }),

  // Calendar
  calendar: (days_ahead = 14) => get<{ items: CalendarItem[] }>(`/api/calendar?days_ahead=${days_ahead}`),
  createCalendar: (subject: string, start: string, end: string, location?: string, body?: string) =>
    post<{ id: string; subject: string }>('/api/calendar/create', { subject, start, end, location, body }),
  updateCalendar: (event_id: string, subject: string, start: string, end: string, location?: string, body?: string) =>
    patch<{ id: string; subject: string }>(`/api/calendar/${encodeURIComponent(event_id)}`, { subject, start, end, location: location ?? '', body: body ?? '' }),
  deleteCalendar: (event_id: string, changekey = '') =>
    del<{ status: string }>(`/api/calendar/${encodeURIComponent(event_id)}`, { changekey }),

  // Tasks
  tasks: () => get<{ tasks: Task[] }>('/api/tasks'),
  createTask: (subject: string, due_date?: string, body?: string, priority?: string) =>
    post<{ id: string; subject: string }>('/api/tasks/create', { subject, due_date, body, priority }),
  completeTask: (task_id: string, changekey: string) =>
    post<{ status: string }>(`/api/tasks/${encodeURIComponent(task_id)}/complete`, { changekey }),
  deleteTask: (task_id: string, changekey: string) =>
    del<{ status: string }>(`/api/tasks/${encodeURIComponent(task_id)}`, { changekey }),
  deleteMail: (mail_uid: string) =>
    del<{ status: string }>(`/api/mails/${encodeURIComponent(mail_uid)}`, {}),

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

  // Graph / Knowledge Map
  graph: (subject: string, text: string) =>
    post<{ nodes: Array<{ id: string; label: string; type: string }>; edges: Array<{ source: string; target: string; label: string }> }>(
      '/api/graph', { subject, text }
    ),

  // DB HAFAS Train Planner
  trainStations: (q: string) =>
    get<{ stations: TrainStation[] }>(`/api/trains/stations?q=${encodeURIComponent(q)}`),
  trainJourneys: (from_id: string, to_id: string, when?: string, results = 5) =>
    get<{ journeys: TrainJourney[] }>(
      `/api/trains/journeys?from_id=${encodeURIComponent(from_id)}&to_id=${encodeURIComponent(to_id)}&results=${results}${when ? `&when=${encodeURIComponent(when)}` : ''}`
    ),

  // Knowledge / RAG Search
  knowledgeSearch: (q: string, n = 3) =>
    get<{ results: KnowledgeResult[] }>(`/api/knowledge/search?q=${encodeURIComponent(q)}&n=${n}`),

  // Ontology / Knowledge Graph
  ontologyEntities: () => get<OntologyEntities>('/api/ontology/entities'),
  ontologySearch: (q: string) =>
    get<{ context: string }>(`/api/ontology/search?q=${encodeURIComponent(q)}`),

  // Chat (SSE streaming)
  chatStream: (message: string, includeContext: boolean = true, messageId: string = ''): ReadableStream<string> => {
    const ctrl = new AbortController()
    return new ReadableStream({
      async start(controller) {
        try {
          const r = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, include_context: includeContext, message_id: messageId }),
            signal: ctrl.signal,
          })
          if (!r.ok || !r.body) {
            _handle401(r.status)
            const msg = r.status === 401 ? 'Sitzung abgelaufen. Bitte neu anmelden.' : `Fehler ${r.status}`
            controller.error(new Error(msg))
            return
          }
          const reader = r.body.getReader()
          const dec = new TextDecoder()
          let pendingEvent = ''
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const chunk = dec.decode(value)
            for (const line of chunk.split('\n')) {
              if (line.startsWith('event: ')) {
                pendingEvent = line.slice(7).trim()
              } else if (line.startsWith('data: ')) {
                // Unescape \n (backslash-n) back to real newlines (encoded by backend _sse())
                const data = line.slice(6).replace(/\\n/g, '\n')
                if (data === '[DONE]') { controller.close(); return }
                // Named SSE events (e.g. "nav") are prefixed with \x00EVENT\x00
                controller.enqueue(pendingEvent ? `\x00${pendingEvent}\x00${data}` : data)
                pendingEvent = ''
              } else if (line === '') {
                pendingEvent = ''
              }
            }
          }
          controller.close()
        } catch (e) {
          controller.error(e)
        }
      },
      cancel() { ctrl.abort() },
    })
  },

  // Meeting Briefing (UC3) — SSE streaming identical to chatStream
  briefingStream: (event: {
    subject: string
    start?: string | null
    end?: string | null
    location?: string | null
    body?: string | null
  }): ReadableStream<string> => {
    const ctrl = new AbortController()
    return new ReadableStream({
      async start(controller) {
        try {
          const r = await fetch('/api/briefing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              subject: event.subject,
              start: event.start ?? '',
              end: event.end ?? '',
              location: event.location ?? '',
              body: event.body ?? '',
            }),
            signal: ctrl.signal,
          })
          if (!r.ok || !r.body) {
            _handle401(r.status)
            controller.error(new Error(`Fehler ${r.status}`))
            return
          }
          const reader = r.body.getReader()
          const dec = new TextDecoder()
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const chunk = dec.decode(value)
            for (const line of chunk.split('\n')) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6).replace(/\\n/g, '\n')
                if (data === '[DONE]') { controller.close(); return }
                controller.enqueue(data)
              }
            }
          }
          controller.close()
        } catch (e) {
          controller.error(e)
        }
      },
      cancel() { ctrl.abort() },
    })
  },

  // Memory API
  memoryFacts: async (params?: {
    category?: string
    min_confidence?: number
    source_ref?: string
  }): Promise<{ facts: MemoryFact[] }> => {
    const q = new URLSearchParams()
    if (params?.category) q.set('category', params.category)
    if (params?.min_confidence != null) q.set('min_confidence', String(params.min_confidence))
    if (params?.source_ref) q.set('source_ref', params.source_ref)
    const qs = q.size ? '?' + q.toString() : ''
    const res = await fetch(`/api/memory/facts${qs}`, { credentials: 'include' })
    if (!res.ok) throw new Error('memory/facts fehlgeschlagen')
    return res.json()
  },

  memoryFeedback: async (factId: string, rating: 'up' | 'down'): Promise<void> => {
    await fetch('/api/memory/feedback', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fact_id: factId, rating }),
    })
  },

  memoryDeleteFact: async (factId: string): Promise<void> => {
    await fetch(`/api/memory/facts/${factId}`, {
      method: 'DELETE',
      credentials: 'include',
    })
  },

  memoryUpdateFact: async (factId: string, text: string, note?: string): Promise<void> => {
    await fetch(`/api/memory/facts/${factId}`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, correction_note: note ?? null }),
    })
  },

  memoryStats: async (): Promise<MemoryStats> => {
    const res = await fetch('/api/memory/stats', { credentials: 'include' })
    if (!res.ok) throw new Error('memory/stats fehlgeschlagen')
    return res.json()
  },
}
