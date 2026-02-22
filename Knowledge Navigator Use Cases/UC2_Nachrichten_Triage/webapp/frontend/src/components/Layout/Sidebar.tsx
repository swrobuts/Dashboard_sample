import { useStore } from '../../store/useStore'
import type { View } from '../../store/useStore'
import { api } from '../../api/client'
import styles from './Sidebar.module.css'

const NAV_ITEMS: Array<{ view: View; label: string; icon: string }> = [
  { view: 'dashboard', label: 'Dashboard', icon: '⊞' },
  { view: 'mails',     label: 'Mails',     icon: '✉' },
  { view: 'calendar',  label: 'Kalender',  icon: '◫' },
  { view: 'tasks',     label: 'Aufgaben',  icon: '✓' },
  { view: 'trains',    label: 'Züge',      icon: '🚄' },
]

interface Props {
  collapsed: boolean
  onCollapse: () => void
}

export function Sidebar({ collapsed, onCollapse }: Props) {
  const { view, setView, user, logout, mails } = useStore()
  const unread = mails.filter((m) => !m.is_read).length

  async function handleLogout() {
    await api.logout().catch(() => {})
    logout()
  }

  return (
    <nav className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''}`}>
      {/* Brand row */}
      <div className={styles.brand}>
        {!collapsed && (
          <div className={styles.brandText}>
            <span className={styles.brandName}>PHIL</span>
            <span className={styles.brandSub}>PIM Dashboard</span>
          </div>
        )}
        <button
          className={styles.collapseBtn}
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
            {!collapsed && <span className={styles.navLabel}>{item.label}</span>}
            {item.view === 'mails' && unread > 0 && (
              <span className={styles.badge}>{unread}</span>
            )}
          </button>
        ))}
      </div>

      {/* Bottom user row */}
      <div className={styles.bottom}>
        {collapsed ? (
          <button className={styles.logoutBtnMini} onClick={handleLogout} title="Abmelden">⏻</button>
        ) : (
          <div className={styles.userRow}>
            <span className={styles.userName}>{user?.username}</span>
            <button className={styles.logoutBtn} onClick={handleLogout} title="Abmelden">⏻</button>
          </div>
        )}
      </div>
    </nav>
  )
}
