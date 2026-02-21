import { create } from 'zustand'
import type { User, TriagedMail, CalendarItem, Task, Category } from '../api/types'

export type View = 'dashboard' | 'mails' | 'calendar' | 'tasks'
export type Selection =
  | { type: 'mail'; item: TriagedMail }
  | { type: 'calendar'; item: CalendarItem }
  | { type: 'task'; item: Task }
  | null

interface AppState {
  // Auth
  user: User | null
  setUser: (u: User | null) => void
  logout: () => void

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
  logout: () => set({
    user: null, mails: [], calendar: [], tasks: [],
    selection: null, view: 'dashboard', mailFilter: 'all',
    loadingMails: false, loadingCalendar: false, loadingTasks: false,
  }),

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
