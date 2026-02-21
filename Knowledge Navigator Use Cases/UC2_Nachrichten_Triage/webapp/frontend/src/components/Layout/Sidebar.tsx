import { useStore } from '../../store/useStore'
import type { View } from '../../store/useStore'
import { api } from '../../api/client'
import styles from './Sidebar.module.css'

const NAV_ITEMS: Array<{ view: View; label: string; icon: string }> = [
  { view: 'dashboard', label: 'Dashboard', icon: '⊞' },
  { view: 'mails', label: 'Mails', icon: '✉' },
  { view: 'calendar', label: 'Kalender', icon: '◫' },
  { view: 'tasks', label: 'Aufgaben', icon: '✓' },
]

interface Props { onOpenPhil: () => void }

export function Sidebar({ onOpenPhil }: Props) {
  const { view, setView, user, setUser, mails } = useStore()
  const unread = mails.filter((m) => !m.is_read).length

  async function handleLogout() {
    await api.logout().catch(() => {})
    setUser(null)
  }

  return (
    <nav className={styles.sidebar}>
      <div className={styles.brand}>
        <span className={styles.brandName}>PHIL</span>
        <span className={styles.brandSub}>PIM Dashboard</span>
      </div>

      <div className={styles.nav}>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.view}
            className={`${styles.navItem} ${view === item.view ? styles.active : ''}`}
            onClick={() => setView(item.view)}
          >
            <span className={styles.navIcon}>{item.icon}</span>
            <span className={styles.navLabel}>{item.label}</span>
            {item.view === 'mails' && unread > 0 && (
              <span className={styles.badge}>{unread}</span>
            )}
          </button>
        ))}
      </div>

      <div className={styles.bottom}>
        <button className={styles.philBtn} onClick={onOpenPhil}>
          <img src="/phil.png" className={styles.philAvatar} alt="PHIL" />
          <span>Frag PHIL</span>
        </button>
        <div className={styles.userRow}>
          <span className={styles.userName}>{user?.username}</span>
          <button className={styles.logoutBtn} onClick={handleLogout} title="Abmelden">⏻</button>
        </div>
      </div>
    </nav>
  )
}
