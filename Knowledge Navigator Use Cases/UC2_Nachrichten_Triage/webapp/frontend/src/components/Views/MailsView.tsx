import { useState, useMemo } from 'react'
import { useStore } from '../../store/useStore'
import { useDataLoader } from '../../hooks/useDataLoader'
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
  const { mails, mailFilter, setMailFilter, loadingMails, sentimentMode, setSentimentMode } = useStore()
  const { loadMails } = useDataLoader()
  const [search, setSearch] = useState('')

  const sorted = useMemo(() => {
    const q = search.toLowerCase()
    return mails
      .filter((m) => {
        if (mailFilter !== 'all' && m.kategorie !== mailFilter) return false
        if (q && !m.subject.toLowerCase().includes(q) && !m.sender.toLowerCase().includes(q)) return false
        return true
      })
      .sort((a, b) => {
        if (a.triageStatus === 'pending' && b.triageStatus !== 'pending') return 1
        if (b.triageStatus === 'pending' && a.triageStatus !== 'pending') return -1
        return (a.priorität ?? 9) - (b.priorität ?? 9)
      })
  }, [mails, mailFilter, search])

  return (
    <div className={styles.view}>
      {/* Row 1: search + sync */}
      <div className={styles.toolbar}>
        <input
          className={styles.search}
          type="search"
          placeholder="Betreff oder Absender suchen…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button
          className={styles.syncBtn}
          onClick={() => loadMails()}
          disabled={loadingMails}
          title="Mails neu laden"
        >
          {loadingMails ? '…' : '↻'}
        </button>
      </div>
      {/* Row 2: category filters + sentiment toggle */}
      <div className={styles.filterBar}>
        {FILTERS.map(({ value, label }) => (
          <button
            key={value}
            className={`${styles.pill} ${mailFilter === value ? styles.active : ''}`}
            onClick={() => setMailFilter(value)}
          >
            {label}
          </button>
        ))}
        <button
          className={`${styles.pill} ${styles.sentimentPill} ${sentimentMode ? styles.sentimentActive : ''}`}
          onClick={() => setSentimentMode(!sentimentMode)}
          title="Mail-Kacheln nach Stimmung einfärben"
        >
          {sentimentMode ? '◑ Sentiment an' : '◑ Sentiment'}
        </button>
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
