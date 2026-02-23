import { useState, useEffect } from 'react'
import { useStore } from '../../store/useStore'
import type { View } from '../../store/useStore'
import { api } from '../../api/client'
import styles from './Sidebar.module.css'

const IconDashboard = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <rect x="1" y="1" width="6" height="6" rx="1"/>
    <rect x="9" y="1" width="6" height="6" rx="1"/>
    <rect x="1" y="9" width="6" height="6" rx="1"/>
    <rect x="9" y="9" width="6" height="6" rx="1"/>
  </svg>
);

const IconMail = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="1" y="3" width="14" height="10" rx="1.5"/>
    <path d="M1 5l7 5 7-5"/>
  </svg>
);

const IconCalendar = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <rect x="1" y="2.5" width="14" height="12" rx="1.5"/>
    <path d="M1 6.5h14"/>
    <path d="M5 1v3M11 1v3"/>
  </svg>
);

const IconTasks = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <path d="M2 4h12M2 8h8M2 12h10"/>
    <circle cx="13" cy="11.5" r="2" fill="none"/>
    <path d="M12 11.5l.8.8 1.6-1.6"/>
  </svg>
);

const IconTrain = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="1" width="10" height="11" rx="2"/>
    <path d="M3 7h10"/>
    <circle cx="5.5" cy="9.5" r="1" fill="currentColor" stroke="none"/>
    <circle cx="10.5" cy="9.5" r="1" fill="currentColor" stroke="none"/>
    <path d="M5 12l-2 3M11 12l2 3"/>
  </svg>
);

const IconMemory = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="8" cy="8" r="6"/>
    <path d="M5 8c0-1.7 1.3-3 3-3s3 1.3 3 3"/>
    <circle cx="6.5" cy="9.5" r="1"/>
    <circle cx="9.5" cy="9.5" r="1"/>
  </svg>
)

const NAV_ITEMS: Array<{ view: View; label: string; icon: React.ReactNode }> = [
  { view: 'dashboard', label: 'Dashboard',  icon: <IconDashboard /> },
  { view: 'mails',     label: 'Mails',      icon: <IconMail /> },
  { view: 'calendar',  label: 'Kalender',   icon: <IconCalendar /> },
  { view: 'tasks',     label: 'Aufgaben',   icon: <IconTasks /> },
  { view: 'trains',    label: 'Züge',       icon: <IconTrain /> },
  { view: 'memory',    label: 'Gedächtnis', icon: <IconMemory /> },
]

interface Props {
  collapsed: boolean
  onCollapse: () => void
}

export function Sidebar({ collapsed, onCollapse }: Props) {
  const { view, setView, user, logout, mails, tasks, calendar, dashDateStr, memoryCount } = useStore()

  // Badge counts
  const unread = mails.filter((m) => !m.is_read).length
  // Calendar: events on the selected dashboard day (local-date aware)
  const calDayCount = calendar.filter((e) => e.start?.slice(0, 10) === dashDateStr).length
  // Tasks: ALL open tasks (not day-filtered — tasks without due date should count too)
  const openTaskCount = tasks.filter((t) => t.status !== 'Completed').length

  // Dark mode toggle
  const [isDark, setIsDark] = useState(() => {
    return typeof window !== 'undefined' && localStorage.getItem('phil-theme') === 'dark'
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light')
    localStorage.setItem('phil-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  // Login duration (minutes since component mount = login time)
  const [loginAt] = useState(() => Date.now())
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 60_000)
    return () => clearInterval(id)
  }, [])
  const loginMinutes = Math.floor((Date.now() - loginAt) / 60_000)

  async function handleLogout() {
    await api.logout().catch(() => {})
    logout()
  }

  return (
    <nav className={`${styles.sidebar} ${collapsed ? styles.mini : ''}`}>
      {/* Brand row */}
      <div className={styles.brand}>
        {!collapsed && (
          <div className={styles.brandText}>
            <span className={styles.brandTitle}>PHIL</span>
            <span className={styles.brandSub}>PIM Dashboard</span>
          </div>
        )}
        <button
          className={styles.toggleBtn}
          onClick={onCollapse}
          title={collapsed ? 'Aufklappen' : 'Einklappen'}
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      {/* Nav items */}
      <div className={styles.nav}>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.view}
            className={`${styles.navItem} ${view === item.view ? styles.active : ''}`}
            onClick={() => setView(item.view)}
            title={collapsed ? item.label : undefined}
          >
            <span className={styles.navIcon}>{item.icon}</span>
            <span className={styles.navLabel}>{item.label}</span>
            {item.view === 'mails' && (
              <span className={styles.badge}>{unread}</span>
            )}
            {item.view === 'tasks' && (
              <span className={styles.badge}>{openTaskCount}</span>
            )}
            {item.view === 'calendar' && (
              <span className={styles.badge}>{calDayCount}</span>
            )}
            {item.view === 'memory' && memoryCount > 0 && (
              <span className={styles.badge}>{memoryCount}</span>
            )}
          </button>
        ))}
      </div>

      {/* Bottom user row */}
      <div className={styles.footer}>
        <div className={styles.userInfo}>
          <span className={styles.user}>{user?.username}</span>
          {!collapsed && (
            <span className={styles.userSince}>
              (seit {loginMinutes < 1 ? '< 1' : loginMinutes} Min.)
            </span>
          )}
        </div>
        <button
          className={styles.themeBtn}
          onClick={() => setIsDark((d) => !d)}
          title={isDark ? 'Heller Modus' : 'Dunkler Modus'}
        >
          {isDark ? '☀' : '☾'}
        </button>
        <button className={styles.logoutBtn} onClick={handleLogout} title="Abmelden">⏻</button>
      </div>
    </nav>
  )
}
