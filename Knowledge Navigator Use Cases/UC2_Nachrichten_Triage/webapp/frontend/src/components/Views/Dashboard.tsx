import { useStore } from '../../store/useStore'
import { useDataLoader } from '../../hooks/useDataLoader'
import type { Category } from '../../api/types'
import styles from './Dashboard.module.css'

const CATS: Array<{ cat: Category; label: string; colorClass: string }> = [
  { cat: 'VIP', label: 'VIP', colorClass: 'vip' },
  { cat: 'Aktion nötig', label: 'Aktion', colorClass: 'aktion' },
  { cat: 'Nur Info', label: 'Info', colorClass: 'info' },
  { cat: 'Ignorieren', label: 'Ignorieren', colorClass: 'ignorieren' },
]

export function Dashboard() {
  const { mails, calendar, tasks, user, loadingMails, setView, setMailFilter } = useStore()
  const { loadCalendar, loadTasks } = useDataLoader()

  const counts = CATS.reduce((acc, { cat }) => {
    acc[cat] = mails.filter((m) => m.kategorie === cat && m.triageStatus === 'done').length
    return acc
  }, {} as Record<Category, number>)

  const today = new Date().toISOString().slice(0, 10)
  const todayEvents = calendar.filter((e) => e.start?.slice(0, 10) === today)
  const urgentTasks = tasks.filter((t) => t.status !== 'Completed').slice(0, 5)

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Morgen' : hour < 18 ? 'Tag' : 'Abend'
  const firstName = user?.username?.split('.')[0] ?? 'Prof'
  const capitalized = firstName.charAt(0).toUpperCase() + firstName.slice(1)

  function goToMails(cat: Category) {
    setMailFilter(cat)
    setView('mails')
  }

  return (
    <div className={styles.dashboard}>
      <header className={styles.header}>
        <h1 className={styles.greeting}>Guten {greeting}, {capitalized}!</h1>
        <p className={styles.date}>
          {new Date().toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' })}
        </p>
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
                {counts[cat]}
                {loadingMails && <span className={styles.tileSpinner}>⟳</span>}
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
                  {e.start
                    ? new Date(e.start).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
                    : ''}
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
                <span className={`${styles.taskPriority} ${styles[(t.priority ?? 'Normal').toLowerCase()]}`} />
                <span className={styles.taskTitle}>{t.subject}</span>
                {t.due_date && <span className={styles.taskDue}>{t.due_date.slice(0, 10)}</span>}
              </div>
            ))}
          </div>
        </section>
      )}

      <div className={user?.ews_connected ? styles.ewsOk : styles.ewsNotice}>
        {user?.ews_connected ? (
          <>
            <span className={styles.ewsDot} />
            <span>Exchange verbunden — Kalender &amp; Aufgaben aktiv</span>
          </>
        ) : (
          <>
            <span>⚠</span>
            <span>
              Kalender &amp; Aufgaben: Exchange nicht verbunden.
              {user?.ews_error && <span className={styles.ewsErrorDetail}> ({user.ews_error})</span>}
            </span>
            <button className={styles.ewsRetry} onClick={() => { loadCalendar(); loadTasks() }}>
              Neu verbinden
            </button>
          </>
        )}
      </div>
    </div>
  )
}
