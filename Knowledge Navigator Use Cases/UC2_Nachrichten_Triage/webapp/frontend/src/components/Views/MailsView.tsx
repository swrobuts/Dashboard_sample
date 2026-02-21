import { useStore } from '../../store/useStore'
import { MailCard } from '../Cards/MailCard'
import styles from './MailsView.module.css'
import type { Category } from '../../api/types'

const FILTERS: Array<{ value: Category | 'all'; label: string }> = [
  { value: 'all', label: 'Alle' },
  { value: 'VIP', label: 'VIP' },
  { value: 'Aktion nötig', label: 'Aktion' },
  { value: 'Nur Info', label: 'Info' },
  { value: 'Ignorieren', label: 'Ignorieren' },
]

export function MailsView() {
  const { mails, mailFilter, setMailFilter, loadingMails } = useStore()

  const filtered = mailFilter === 'all'
    ? mails
    : mails.filter((m) => m.kategorie === mailFilter)

  const sorted = [...filtered].sort((a, b) => {
    if (a.triageStatus === 'pending' && b.triageStatus !== 'pending') return 1
    if (b.triageStatus === 'pending' && a.triageStatus !== 'pending') return -1
    return (a.priorität ?? 9) - (b.priorität ?? 9)
  })

  return (
    <div className={styles.view}>
      <header className={styles.header}>
        <h1 className={styles.title}>Mails</h1>
        {loadingMails && <span className={styles.loading}>Lade…</span>}
      </header>

      <div className={styles.filters}>
        {FILTERS.map(({ value, label }) => (
          <button
            key={value}
            className={`${styles.pill} ${mailFilter === value ? styles.active : ''}`}
            onClick={() => setMailFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className={styles.list}>
        {sorted.length === 0 ? (
          <p className={styles.empty}>{loadingMails ? 'Lade Mails…' : 'Keine Mails.'}</p>
        ) : (
          sorted.map((mail) => <MailCard key={mail.id} mail={mail} />)
        )}
      </div>
    </div>
  )
}
