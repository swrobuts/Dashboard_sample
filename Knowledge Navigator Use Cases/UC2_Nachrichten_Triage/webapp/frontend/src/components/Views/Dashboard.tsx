import { useState, useEffect } from 'react'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import type { Category, Task, CalendarItem, KnowledgeResult } from '../../api/types'
import styles from './Dashboard.module.css'

const CATS: Array<{ cat: Category; label: string; colorClass: string }> = [
  { cat: 'VIP', label: 'VIP', colorClass: 'vip' },
  { cat: 'Aktion nötig', label: 'Aktion', colorClass: 'aktion' },
  { cat: 'Nur Info', label: 'Info', colorClass: 'info' },
  { cat: 'Ignorieren', label: 'Ignorieren', colorClass: 'ignorieren' },
]

type TaskGroup = 'none' | 'priority' | 'due_date'
const PRIO_ORDER: Record<string, number> = { High: 0, Normal: 1, Low: 2 }
const PRIO_LABEL: Record<string, string> = { High: 'Hoch', Normal: 'Normal', Low: 'Niedrig' }

// ── Helpers ───────────────────────────────────────────────────────────────────
function toLocalDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatDashDate(d: Date): string {
  const today = toLocalDateStr(new Date())
  const tomorrow = toLocalDateStr(new Date(Date.now() + 86400000))
  const ds = toLocalDateStr(d)
  if (ds === today) return 'Heute'
  if (ds === tomorrow) return 'Morgen'
  return d.toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' })
}

function addDays(d: Date, n: number): Date {
  const nd = new Date(d)
  nd.setDate(nd.getDate() + n)
  return nd
}

// ── Schedule helpers ──────────────────────────────────────────────────────────
function minsOf(dateStr: string) {
  const d = new Date(dateStr)
  return d.getHours() * 60 + d.getMinutes()
}
function fmtTime(mins: number) {
  return `${String(Math.floor(mins / 60)).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`
}
function fmtDur(mins: number) {
  if (mins < 60) return `${mins} min`
  const h = Math.floor(mins / 60), m = mins % 60
  return m ? `${h}h ${m}min` : `${h}h`
}

// ── Day Schedule ──────────────────────────────────────────────────────────────
type ScheduleBlock =
  | { type: 'event'; start: number; end: number; item: CalendarItem }
  | { type: 'free';  start: number; end: number }

function DaySchedule({ events, isToday }: { events: CalendarItem[]; isToday: boolean }) {
  const now = new Date()
  const nowMins = now.getHours() * 60 + now.getMinutes()

  const sorted = [...events]
    .filter((e) => e.start && e.end)
    .sort((a, b) => new Date(a.start!).getTime() - new Date(b.start!).getTime())

  if (sorted.length === 0) {
    return (
      <div className={styles.schedEmpty}>
        Keine Termine — ganzer Tag frei 🎉
      </div>
    )
  }

  const DAY_START = 7 * 60, DAY_END = 21 * 60
  const blocks: ScheduleBlock[] = []
  let cursor = DAY_START

  for (const e of sorted) {
    const s = minsOf(e.start!), en = minsOf(e.end!)
    if (s > cursor + 14) blocks.push({ type: 'free', start: cursor, end: s })
    blocks.push({ type: 'event', start: s, end: en, item: e })
    cursor = Math.max(cursor, en)
  }
  if (cursor < DAY_END) blocks.push({ type: 'free', start: cursor, end: DAY_END })

  return (
    <div className={styles.sched}>
      {blocks.map((b, i) => {
        if (b.type === 'free') {
          const dur = b.end - b.start
          if (dur < 20) return null
          const isNow = isToday && nowMins >= b.start && nowMins < b.end
          return (
            <div key={i} className={`${styles.schedFree} ${isNow ? styles.schedFreeNow : ''}`}>
              <span className={styles.schedFreeTime}>{fmtTime(b.start)} – {fmtTime(b.end)}</span>
              <span className={styles.schedFreeDur}>Frei · {fmtDur(dur)}</span>
              {isNow && <span className={styles.schedFreeNowDot} />}
            </div>
          )
        }

        const { item, start, end } = b as { type: 'event'; start: number; end: number; item: CalendarItem }
        const dur = end - start
        const isPast = isToday && end < nowMins
        const isNow  = isToday && start <= nowMins && nowMins < end
        return (
          <div key={i} className={`${styles.schedEvent} ${isPast ? styles.schedEventPast : ''} ${isNow ? styles.schedEventNow : ''}`}>
            <div className={styles.schedEventBar} />
            <div className={styles.schedEventTime}>
              <span className={styles.schedEventStart}>{fmtTime(start)}</span>
              <span className={styles.schedEventDur}>{fmtDur(dur)}</span>
            </div>
            <div className={styles.schedEventBody}>
              <span className={styles.schedEventTitle}>{item.subject}</span>
              {item.location && !item.location.match(/^https?:\/\//i) && (
                <span className={styles.schedEventLoc}>📍 {item.location}</span>
              )}
            </div>
            {isNow && <span className={styles.schedLiveTag}>Jetzt</span>}
          </div>
        )
      })}
    </div>
  )
}

// ── Task grouping ─────────────────────────────────────────────────────────────
function groupTasks(tasks: Task[], groupBy: TaskGroup): Array<{ label: string; items: Task[] }> {
  if (groupBy === 'none') return [{ label: '', items: tasks }]

  if (groupBy === 'priority') {
    const groups: Record<string, Task[]> = { High: [], Normal: [], Low: [] }
    for (const t of tasks) groups[t.priority ?? 'Normal']?.push(t)
    return Object.entries(groups)
      .sort(([a], [b]) => (PRIO_ORDER[a] ?? 1) - (PRIO_ORDER[b] ?? 1))
      .filter(([, items]) => items.length > 0)
      .map(([label, items]) => ({ label: PRIO_LABEL[label] ?? label, items }))
  }

  // due_date grouping
  const today = toLocalDateStr(new Date())
  const weekEnd = toLocalDateStr(addDays(new Date(), 7))
  const groups: Record<string, Task[]> = {
    'Überfällig': [], 'Heute': [], 'Diese Woche': [], 'Später': [], 'Kein Datum': [],
  }
  for (const t of tasks) {
    if (!t.due_date) { groups['Kein Datum'].push(t); continue }
    const due = t.due_date.slice(0, 10)
    if (due < today) groups['Überfällig'].push(t)
    else if (due === today) groups['Heute'].push(t)
    else if (due <= weekEnd) groups['Diese Woche'].push(t)
    else groups['Später'].push(t)
  }
  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }))
}

// ── Main Component ────────────────────────────────────────────────────────────
export function Dashboard() {
  const { mails, calendar, tasks, user, loadingMails, setView, setMailFilter, removeTask } = useStore()
  const [completing, setCompleting] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [taskError, setTaskError] = useState<string | null>(null)
  const [taskGroup, setTaskGroup] = useState<TaskGroup>('none')

  // ── Date navigation ─────────────────────────────────────────────────────
  const [dashDate, setDashDate] = useState(new Date())
  const dashDateStr = toLocalDateStr(dashDate)
  const isToday = dashDateStr === toLocalDateStr(new Date())

  // ── Meeting contexts (knowledge search per event) ─────────────────────
  const [meetingContexts, setMeetingContexts] = useState<Record<string, KnowledgeResult[]>>({})
  const [loadingMeetings, setLoadingMeetings] = useState(false)

  const dashEvents = calendar
    .filter((e) => e.start?.slice(0, 10) === dashDateStr)
    .sort((a, b) => new Date(a.start!).getTime() - new Date(b.start!).getTime())

  useEffect(() => {
    if (dashEvents.length === 0) { setMeetingContexts({}); return }
    setLoadingMeetings(true)
    Promise.all(
      dashEvents.map((ev) =>
        api.knowledgeSearch(ev.subject, 2)
          .then(({ results }) => ({ id: ev.id, results }))
          .catch(() => ({ id: ev.id, results: [] as KnowledgeResult[] }))
      )
    ).then((all) => {
      const map: Record<string, KnowledgeResult[]> = {}
      all.forEach(({ id, results }) => { map[id] = results })
      setMeetingContexts(map)
    }).finally(() => setLoadingMeetings(false))
  }, [dashDateStr, calendar.length])

  const counts = CATS.reduce((acc, { cat }) => {
    acc[cat] = mails.filter((m) => m.kategorie === cat && m.triageStatus === 'done').length
    return acc
  }, {} as Record<Category, number>)

  const urgentTasks = tasks.filter((t) => t.status !== 'Completed').slice(0, 12)
  const groupedTasks = groupTasks(urgentTasks, taskGroup)

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Morgen' : hour < 18 ? 'Tag' : 'Abend'
  const rawFirst = user?.username?.split('.')[0] ?? ''
  const displayName = user?.first_name
    ?? (rawFirst ? rawFirst.charAt(0).toUpperCase() + rawFirst.slice(1) : 'Prof')

  function goToMails(cat: Category) {
    setMailFilter(cat)
    setView('mails')
  }

  async function quickComplete(task: Task) {
    setCompleting(task.id)
    try {
      await api.completeTask(task.id, task.changekey)
      removeTask(task.id)
    } catch (e) {
      console.error(e)
      setTaskError(task.id)
      setTimeout(() => setTaskError((cur) => cur === task.id ? null : cur), 2000)
    } finally { setCompleting(null) }
  }

  async function quickDelete(task: Task) {
    setDeleting(task.id)
    try {
      await api.deleteTask(task.id, task.changekey)
      removeTask(task.id)
    } catch (e) {
      console.error(e)
      setTaskError(task.id)
      setTimeout(() => setTaskError((cur) => cur === task.id ? null : cur), 2000)
    } finally { setDeleting(null) }
  }

  return (
    <div className={styles.dashboard}>
      <header className={styles.header}>
        <h1 className={styles.greeting}>Guten {greeting}, {displayName}!</h1>
      </header>

      {/* Mail tiles */}
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
                {counts[cat]}
                {loadingMails && <span className={styles.tileSpinner}>⟳</span>}
              </span>
              <span className={styles.tileLabel}>{label}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Two-column: schedule + (tasks + gespräche) */}
      <div className={styles.twoCol}>

        {/* ── Left: Day schedule with date navigation ── */}
        <section className={styles.section}>
          <div className={styles.schedHeader}>
            <h2 className={styles.sectionTitle}>Tagesplan</h2>
            <div className={styles.dateNav}>
              <button className={styles.dateNavBtn} onClick={() => setDashDate(d => addDays(d, -1))}>‹</button>
              <span className={`${styles.dateNavLabel} ${isToday ? styles.dateNavToday : ''}`}>
                {formatDashDate(dashDate)}
              </span>
              <button className={styles.dateNavBtn} onClick={() => setDashDate(d => addDays(d, 1))}>›</button>
              {!isToday && (
                <button className={styles.dateNavTodayBtn} onClick={() => setDashDate(new Date())}>Heute</button>
              )}
            </div>
          </div>
          <DaySchedule events={dashEvents} isToday={isToday} />
        </section>

        {/* ── Right: Tasks + Gespräche ── */}
        <section className={styles.section}>

          {/* Tasks sub-section */}
          <div className={styles.subSection}>
            <div className={styles.subSectionHeader}>
              <h2 className={styles.sectionTitle}>Offene Aufgaben</h2>
              <div className={styles.taskGroupBar}>
                {(['none', 'priority', 'due_date'] as TaskGroup[]).map((g) => (
                  <button
                    key={g}
                    className={`${styles.taskGroupBtn} ${taskGroup === g ? styles.taskGroupBtnActive : ''}`}
                    onClick={() => setTaskGroup(g)}
                  >
                    {g === 'none' ? 'Alle' : g === 'priority' ? 'Prio' : 'Datum'}
                  </button>
                ))}
              </div>
            </div>
            {urgentTasks.length === 0 ? (
              <p className={styles.noTasks}>Keine offenen Aufgaben.</p>
            ) : (
              <div className={styles.taskList}>
                {groupedTasks.map(({ label, items }) => (
                  <div key={label}>
                    {label && <div className={styles.taskGroupHeader}>{label}</div>}
                    {items.map((t) => (
                      <div key={t.id} className={styles.taskItem}>
                        <span className={`${styles.taskDot} ${styles[(t.priority ?? 'Normal').toLowerCase()]}`} />
                        <div className={styles.taskBody}>
                          <span className={styles.taskTitle}>{t.subject}</span>
                          {t.due_date && <span className={styles.taskDue}>{t.due_date.slice(0, 10)}</span>}
                        </div>
                        {user?.ews_connected && (
                          <div className={styles.taskActions}>
                            <button
                              className={`${styles.taskDoneBtn}${taskError === t.id ? ` ${styles.taskDoneErr}` : ''}`}
                              onClick={() => quickComplete(t)}
                              disabled={completing === t.id || deleting === t.id}
                              title={taskError === t.id ? 'Fehler' : 'Als erledigt markieren'}
                            >
                              {completing === t.id ? '…' : '✓'}
                            </button>
                            <button
                              className={`${styles.taskDelBtn}${taskError === t.id ? ` ${styles.taskDoneErr}` : ''}`}
                              onClick={() => quickDelete(t)}
                              disabled={completing === t.id || deleting === t.id}
                              title="Aus Exchange löschen"
                            >
                              {deleting === t.id ? '…' : '✕'}
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Gespräche mit Personen sub-section */}
          <div className={styles.subSection}>
            <h2 className={styles.sectionTitle} style={{ marginBottom: '.5rem', marginTop: '.75rem' }}>
              Gespräche mit Personen
              {loadingMeetings && <span className={styles.tileSpinner} style={{ marginLeft: '.4rem', fontSize: '.75rem' }}>⟳</span>}
            </h2>
            {dashEvents.length === 0 ? (
              <div className={styles.noTasks}>Keine Termine {isToday ? 'heute' : 'an diesem Tag'}.</div>
            ) : (
              <div className={styles.gesprachList}>
                {dashEvents.map((ev) => {
                  const relMails = meetingContexts[ev.id] ?? []
                  const startTime = ev.start ? new Date(ev.start).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : ''
                  const endTime = ev.end ? new Date(ev.end).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : ''
                  return (
                    <div key={ev.id} className={styles.gesprachItem}>
                      <div className={styles.gesprachHeader}>
                        <span className={styles.gesprachTime}>{startTime} – {endTime}</span>
                        <span className={styles.gesprachTitle}>{ev.subject}</span>
                        {ev.location && (
                          <span className={styles.gesprachLoc}>
                            {ev.location.match(/^https?:\/\//i) ? '🔗 Online' : `📍 ${ev.location}`}
                          </span>
                        )}
                      </div>
                      {relMails.length > 0 ? (
                        <div className={styles.gesprachMails}>
                          <span className={styles.gesprachMailsLabel}>Relevante Unterlagen:</span>
                          {relMails.map((m) => (
                            <div key={m.id} className={styles.gesprachMail}>
                              <span className={styles.gesprachMailSender}>{m.sender}</span>
                              <span className={styles.gesprachMailSubject}>{m.subject}</span>
                              {m.summary && <span className={styles.gesprachMailSummary}>{m.summary}</span>}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className={styles.gesprachNoMails}>Keine relevanten Unterlagen verknüpft.</div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

        </section>
      </div>
    </div>
  )
}
