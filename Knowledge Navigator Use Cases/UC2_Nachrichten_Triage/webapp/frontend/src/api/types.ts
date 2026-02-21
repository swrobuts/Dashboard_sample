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
