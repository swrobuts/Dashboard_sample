export interface User {
  username: string
  first_name?: string
  institution: string
  inbox_count: number
  unread_count?: number
  drafts_count?: number
  sent_today?: number
  ews_connected: boolean
  ews_error?: string | null
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
  stimmung?: number   // -1 (sehr negativ) … 0 (neutral) … +1 (sehr positiv)
  // ui
  id: string
  triageStatus: 'pending' | 'done' | 'error'
  mail_uid?: string   // IMAP UID for deletion
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

export interface TrainStation {
  id: string
  name: string
}

export interface TrainJourney {
  departure: string | null
  arrival: string | null
  delay_dep: number    // minutes
  delay_arr: number    // minutes
  changes: number
  products: string[]
  price: number | null
}

export interface KnowledgeResult {
  id: string
  subject: string
  sender: string
  date: string
  kategorie: string
  summary: string
  score: number
}

export interface AttachmentIn {
  filename: string
  mime_type: string
  data_b64: string
}

export interface OntologyEntities {
  persons: Array<{ name: string; mail_count: number }>
  projects: Array<{ description: string }>
  tasks: Array<{ description: string }>
  deadlines: Array<{ date: string }>
}
