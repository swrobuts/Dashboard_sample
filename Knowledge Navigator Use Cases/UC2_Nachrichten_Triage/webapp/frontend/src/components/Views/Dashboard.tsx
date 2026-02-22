import { useState } from 'react'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import type { Category, Task, CalendarItem } from '../../api/types'
import styles from './Dashboard.module.css'

const CATS: Array<{ cat: Category; label: string; colorClass: string }> = [
  { cat: 'VIP', label: 'VIP', colorClass: 'vip' },
  { cat: 'Aktion nötig', label: 'Aktion', colorClass: 'aktion' },
  { cat: 'Nur Info', label: 'Info', colorClass: 'info' },
  { cat: 'Ignorieren', label: 'Ignorieren', colorClass: 'ignorieren' },
]

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

function DaySchedule({ events }: { events: CalendarItem[] }) {
  const now = new Date()
  const nowMins = now.getHours() * 60 + now.getMinutes()

  const sorted = [...events]
    .filter((e) => e.start && e.end)
    .sort((a, b) => new Date(a.start!).getTime() - new Date(b.start!).getTime())

  if (sorted.length === 0) {
    return (
      <div className={styles.schedEmpty}>
        Heute keine Termine — ganzer Tag frei 🎉
      </div>
    )
  }

  // Build blocks: free gaps + events
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
          const isNow = nowMins >= b.start && nowMins < b.end
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
        const isPast = end < nowMins
        const isNow  = start <= nowMins && nowMins < end
        return (
          <div key={i} className={`${styles.schedEvent} ${isPast ? styles.schedEventPast : ''} ${isNow ? styles.schedEventNow : ''}`}>
            <div className={styles.schedEventBar} />
            <div className={styles.schedEventTime}>
              <span className={styles.schedEventStart}>{fmtTime(start)}</span>
              <span className={styles.schedEventDur}>{fmtDur(dur)}</span>
            </div>
            <div className={styles.schedEventBody}>
              <span className={styles.schedEventTitle}>{item.subject}</span>
              {item.location && <span className={styles.schedEventLoc}>📍 {item.location}</span>}
            </div>
            {isNow && <span className={styles.schedLiveTag}>Jetzt</span>}
          </div>
        )
      })}
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────
export function Dashboard() {
  const { mails, calendar, tasks, user, loadingMails, setView, setMailFilter, removeTask } = useStore()
  const [completing, setCompleting] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [taskError, setTaskError] = useState<string | null>(null)

  const counts = CATS.reduce((acc, { cat }) => {
    acc[cat] = mails.filter((m) => m.kategorie === cat && m.triageStatus === 'done').length
    return acc
  }, {} as Record<Category, number>)

  const today = new Date().toISOString().slice(0, 10)
  const todayEvents = calendar
    .filter((e) => e.start?.slice(0, 10) === today)
    .sort((a, b) => new Date(a.start!).getTime() - new Date(b.start!).getTime())

  const urgentTasks = tasks.filter((t) => t.status !== 'Completed').slice(0, 8)

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

      {/* Two-column: schedule + tasks */}
      <div className={styles.twoCol}>
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Tagesplan</h2>
          <DaySchedule events={todayEvents} />
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Offene Aufgaben</h2>
          {urgentTasks.length === 0 ? (
            <p className={styles.noTasks}>Keine offenen Aufgaben.</p>
          ) : (
            <div className={styles.taskList}>
              {urgentTasks.map((t) => (
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
          )}
        </section>
      </div>
    </div>
  )
}
