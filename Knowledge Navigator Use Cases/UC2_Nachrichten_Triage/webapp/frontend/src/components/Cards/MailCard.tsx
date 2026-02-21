import { useStore } from '../../store/useStore'
import type { TriagedMail } from '../../api/types'
import styles from './MailCard.module.css'

const CAT_COLORS: Record<string, string> = {
  'VIP': 'vip',
  'Aktion nötig': 'aktion',
  'Nur Info': 'info',
  'Ignorieren': 'ignorieren',
}
const CAT_BORDER: Record<string, string> = {
  'VIP': 'vipBorder',
  'Aktion nötig': 'aktionBorder',
  'Nur Info': 'infoBorder',
  'Ignorieren': 'ignorierenBorder',
}

interface Props { mail: TriagedMail }

export function MailCard({ mail }: Props) {
  const { selection, setSelection } = useStore()
  const isSelected = selection?.type === 'mail' && selection.item.id === mail.id
  const colorClass = CAT_COLORS[mail.kategorie] ?? 'info'
  const borderClass = mail.triageStatus === 'done' ? (styles[CAT_BORDER[mail.kategorie] ?? ''] ?? '') : ''

  return (
    <div
      className={`${styles.card} ${borderClass} ${isSelected ? styles.selected : ''}`}
      onClick={() => setSelection({ type: 'mail', item: mail })}
    >
      <div className={styles.header}>
        <span className={`${styles.badge} ${styles[colorClass]}`}>{mail.kategorie}</span>
        {mail.triageStatus === 'pending' && <span className={styles.spinner}>⟳</span>}
        <span className={styles.date}>
          {mail.datetime_received
            ? new Date(mail.datetime_received).toLocaleDateString('de-DE', { day: '2-digit', month: 'short' })
            : ''}
        </span>
      </div>
      <p className={styles.subject}>{mail.subject}</p>
      <p className={styles.sender}>{mail.sender}</p>
      {mail.zusammenfassung && (
        <p className={styles.summary}>{mail.zusammenfassung}</p>
      )}
    </div>
  )
}
