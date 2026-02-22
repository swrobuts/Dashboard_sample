import type { User, TriagedMail, CalendarItem, Task, TrainStation, TrainJourney, KnowledgeResult, OntologyEntities } from './types'

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
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

async function del<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'DELETE',
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
  login: (username: string, password: string, institution: string, exchange_email?: string) =>
    post<User & { status: string }>('/api/auth/login', { username, password, institution, exchange_email }),
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

  // Tasks
  tasks: () => get<{ tasks: Task[] }>('/api/tasks'),
  createTask: (subject: string, due_date?: string, body?: string, priority?: string) =>
    post<{ id: string; subject: string }>('/api/tasks/create', { subject, due_date, body, priority }),
  completeTask: (task_id: string, changekey: string) =>
    post<{ status: string }>(`/api/tasks/${task_id}/complete`, { changekey }),
  deleteTask: (task_id: string, changekey: string) =>
    del<{ status: string }>(`/api/tasks/${task_id}`, { changekey }),

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
  chatStream: (message: string, include_context = true): ReadableStream<string> => {
    const ctrl = new AbortController()
    return new ReadableStream({
      async start(controller) {
        try {
          const r = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, include_context }),
            signal: ctrl.signal,
          })
          if (!r.ok || !r.body) {
            const msg = r.status === 401 ? 'Sitzung abgelaufen. Bitte neu anmelden.' : `Fehler ${r.status}`
            controller.error(new Error(msg))
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
                const data = line.slice(6)
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
}
