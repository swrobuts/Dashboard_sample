import { useRef, useState } from 'react'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
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
  const { selection, setSelection, removeMail, setPhilOpen, sentimentMode } = useStore()
  const isSelected = selection?.type === 'mail' && selection.item.id === mail.id
  const colorClass = CAT_COLORS[mail.kategorie] ?? 'info'
  const borderClass = mail.triageStatus === 'done' ? (styles[CAT_BORDER[mail.kategorie] ?? ''] ?? '') : ''

  // Sentiment coloring — background tint + left-border accent
  const sentimentStyle: React.CSSProperties = {}
  let activeBorderClass = borderClass
  if (sentimentMode && mail.triageStatus === 'done' && mail.stimmung !== undefined) {
    const v = Math.min(Math.abs(mail.stimmung), 1)
    if (mail.stimmung > 0.1) {
      sentimentStyle.background = `rgba(34,197,94,${(v * 0.28).toFixed(2)})`
      sentimentStyle.borderLeftColor = `rgb(${Math.round(22 + (1-v)*60)},${Math.round(163 - (1-v)*40)},74)`
      activeBorderClass = ''
    } else if (mail.stimmung < -0.1) {
      sentimentStyle.background = `rgba(239,68,68,${(v * 0.28).toFixed(2)})`
      sentimentStyle.borderLeftColor = `rgb(${Math.round(220 - (1-v)*30)},${Math.round(38 + (1-v)*20)},38)`
      activeBorderClass = ''
    }
  }

  const [ttsState, setTtsState] = useState<'idle' | 'loading' | 'playing'>('idle')
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)

  async function handleVoice(e: React.MouseEvent) {
    e.stopPropagation()

    // Pause if currently playing
    if (ttsState === 'playing' && audioRef.current) {
      audioRef.current.pause()
      setTtsState('idle')
      return
    }

    const text = mail.zusammenfassung || mail.subject
    if (!text) return

    setTtsState('loading')
    try {
      // Clean up any previous audio
      if (audioRef.current) { audioRef.current.pause() }
      if (audioUrlRef.current) { URL.revokeObjectURL(audioUrlRef.current) }

      const url = await api.tts(text)
      audioUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onplay = () => setTtsState('playing')
      audio.onpause = () => setTtsState('idle')
      audio.onended = () => {
        setTtsState('idle')
        URL.revokeObjectURL(url)
        audioUrlRef.current = null
        audioRef.current = null
      }
      audio.play()
    } catch {
      setTtsState('idle')
    }
  }

  function handleGraph(e: React.MouseEvent) {
    e.stopPropagation()
    setSelection({ type: 'mail', item: mail })
    setPhilOpen(true)
  }

  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation()
    removeMail(mail.id)
  }

  return (
    <div
      className={`${styles.card} ${activeBorderClass} ${isSelected ? styles.selected : ''}`}
      style={sentimentStyle}
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
        <div className={styles.actions}>
          <button
            className={`${styles.actionBtn} ${ttsState === 'playing' ? styles.actionBtnPlaying : ''}`}
            onClick={handleVoice}
            disabled={ttsState === 'loading'}
            title={ttsState === 'playing' ? 'Pause' : 'Vorlesen'}
          >
            {ttsState === 'loading' ? '…' : ttsState === 'playing' ? '⏸' : '▶'}
          </button>
          <button className={styles.actionBtn} onClick={handleGraph} title="Als Wissensgraph">🕸</button>
          <button className={`${styles.actionBtn} ${styles.deleteBtn}`} onClick={handleDelete} title="Entfernen">🗑</button>
        </div>
      </div>
      <p className={styles.subject}>{mail.subject}</p>
      <p className={styles.sender}>{mail.sender}</p>
      {mail.zusammenfassung && (
        <p className={styles.summary}>{mail.zusammenfassung}</p>
      )}
    </div>
  )
}
