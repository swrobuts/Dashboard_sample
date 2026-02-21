import type { User, TriagedMail, CalendarItem, Task } from './types'

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
        try {
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
        } catch (e) {
          controller.error(e)
        }
      },
      cancel() { ctrl.abort() },
    })
  },
}
