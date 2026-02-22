import { useState, useMemo, useEffect } from 'react'
import { Sidebar } from './Sidebar'
import { PhilPanel } from '../Phil/PhilPanel'
import { useStore } from '../../store/useStore'
import styles from './AppShell.module.css'

const VIEW_LABEL: Record<string, string> = {
  dashboard: 'Dashboard',
  mails: 'Mails',
  calendar: 'Kalender',
  tasks: 'Aufgaben',
  trains: 'Zugverbindungen',
}

interface Props { children: React.ReactNode }

export function AppShell({ children }: Props) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const { view, user, calendar, mails, tasks, philOpen, setPhilOpen } = useStore()

  // View-specific counters
  const today = new Date().toISOString().slice(0, 10)
  const todayEventCount = useMemo(
    () => calendar.filter((e) => e.start?.slice(0, 10) === today).length,
    [calendar, today],
  )
  const openTaskCount = useMemo(
    () => tasks.filter((t) => t.status !== 'Completed').length,
    [tasks],
  )
  const unreadMailCount = useMemo(
    () => mails.filter((m) => !m.is_read).length,
    [mails],
  )

  const nextEvent = useMemo(() => {
    const now = new Date()
    return calendar
      .filter((e) => e.start && new Date(e.start) > now)
      .sort((a, b) => new Date(a.start!).getTime() - new Date(b.start!).getTime())[0] ?? null
  }, [calendar])

  // Live countdown — updates every minute
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 60_000)
    return () => clearInterval(id)
  }, [])

  function timeUntil(start: string): string {
    const diff = new Date(start).getTime() - Date.now()
    if (diff <= 0) return ''
    const mins = Math.floor(diff / 60_000)
    if (mins < 60) return `in ${mins} min`
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return m > 0 ? `in ${h}h ${m}min` : `in ${h}h`
  }

  function extractUrl(text: string): string | null {
    const m = text.match(/https?:\/\/\S+/)
    return m ? m[0] : null
  }

  return (
    <div
      className={styles.shell}
      data-phil-open={philOpen ? 'true' : 'false'}
      data-sidebar-collapsed={sidebarCollapsed ? 'true' : 'false'}
    >
      <Sidebar
        collapsed={sidebarCollapsed}
        onCollapse={() => setSidebarCollapsed((v) => !v)}
      />

      <div className={styles.contentWrap}>
        <header className={styles.topbar}>
          {view === 'dashboard' ? (
            <div className={styles.pageTitleDate}>
              <span className={styles.pageTitleDay}>
                {new Date().toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' })}
              </span>
              <span className={styles.pageTitleTime}>
                {new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          ) : (
            <div className={styles.titleWithStats}>
              <h1 className={styles.pageTitle}>{VIEW_LABEL[view] ?? view}</h1>
              {view === 'mails' && (
                <div className={styles.viewStats}>
                  <span className={styles.viewStat}>📥 {user?.inbox_count ?? 0}</span>
                  <span className={styles.viewStat}>📬 {unreadMailCount} ungelesen</span>
                  {(user?.drafts_count ?? 0) > 0 && (
                    <span className={styles.viewStat}>📝 {user!.drafts_count} Entwürfe</span>
                  )}
                  {(user?.sent_today ?? 0) > 0 && (
                    <span className={styles.viewStat}>📤 {user!.sent_today} heute</span>
                  )}
                </div>
              )}
              {view === 'calendar' && (
                <div className={styles.viewStats}>
                  <span className={styles.viewStat}>📅 {todayEventCount} heute</span>
                </div>
              )}
              {view === 'tasks' && (
                <div className={styles.viewStats}>
                  <span className={styles.viewStat}>✓ {openTaskCount} offen</span>
                </div>
              )}
            </div>
          )}

          {/* Next appointment pill */}
          {nextEvent && (() => {
            const meetingUrl = extractUrl(nextEvent.location || '') || extractUrl(nextEvent.body || '')
            const remaining = timeUntil(nextEvent.start!)
            return (
              <div className={styles.nextEventPill}>
                <span className={styles.nextEventIcon}>📅</span>
                <span className={styles.nextEventTime}>
                  {new Date(nextEvent.start!).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
                </span>
                <span className={styles.nextEventTitle}>{nextEvent.subject}</span>
                {remaining && <span className={styles.nextEventRemaining}>{remaining}</span>}
                {meetingUrl ? (
                  <a href={meetingUrl} target="_blank" rel="noopener noreferrer" className={styles.nextEventLink}>
                    🔗 Beitreten
                  </a>
                ) : nextEvent.location ? (
                  <span className={styles.nextEventLoc}>· {nextEvent.location}</span>
                ) : null}
              </div>
            )
          })()}

          <div className={styles.topbarRight}>
            {user && (
              <div className={`${styles.ewsPill} ${!user.ews_connected ? styles.ewsPillErr : ''}`}>
                <span className={`${styles.ewsPillDot} ${!user.ews_connected ? styles.ewsPillErrDot : ''}`} />
                {user.ews_connected ? 'Exchange verbunden' : 'Exchange getrennt'}
              </div>
            )}
            <button
              className={`${styles.philBtn} ${philOpen ? styles.philBtnActive : ''}`}
              onClick={() => setPhilOpen(!philOpen)}
              title={philOpen ? 'PHIL schließen' : 'PHIL öffnen'}
            >
              <img src="/phil.png" alt="PHIL" className={styles.philBtnAvatar} />
              <span className={styles.philBtnLabel}>PHIL</span>
            </button>
          </div>
        </header>

        <main className={styles.content}>{children}</main>
      </div>

      <PhilPanel open={philOpen} onClose={() => setPhilOpen(false)} />

      {philOpen && (
        <div className={`${styles.backdrop} ${styles.mobileOnly}`} onClick={() => setPhilOpen(false)} />
      )}
    </div>
  )
}
