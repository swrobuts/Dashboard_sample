import { useState, useRef, useEffect } from 'react'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import styles from './PhilPanel.module.css'

interface ChatMessage { role: 'user' | 'phil'; text: string }

interface Props { open: boolean; onClose: () => void }

export function PhilPanel({ open, onClose }: Props) {
  const { selection, mails } = useStore()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const contextLabel = selection
    ? selection.type === 'mail'
      ? `Mail: "${selection.item.subject.slice(0, 50)}"`
      : selection.type === 'calendar'
      ? `Termin: "${selection.item.subject.slice(0, 50)}"`
      : `Aufgabe: "${selection.item.subject.slice(0, 50)}"`
    : null

  const quickActions: string[] = selection?.type === 'mail'
    ? ['Zusammenfassen', 'Antwort formulieren', 'Priorität begründen']
    : selection?.type === 'calendar'
    ? ['Vorbereitung checken', 'Agenda vorschlagen', 'Konflikt prüfen']
    : selection?.type === 'task'
    ? ['Aufgabe beschreiben', 'Aufwand schätzen', 'Unteraufgaben vorschlagen']
    : ['Was steht heute an?', 'Wichtigste Aufgaben', 'Freie Slots finden']

  async function send(text: string) {
    if (!text.trim() || streaming) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text }])
    setStreaming(true)

    // Build context from loaded store data (reliable — no extra IMAP fetch)
    const doneMails = mails.filter((m) => m.triageStatus === 'done').slice(0, 8)
    const mailSummary = doneMails.length > 0
      ? `[Postfach — ${doneMails.length} triagierte Mails]\n` +
        doneMails.map((m) =>
          `• ${m.kategorie}: "${m.subject}" | Von: ${m.sender}${m.zusammenfassung ? ' | ' + m.zusammenfassung : ''}`
        ).join('\n')
      : ''

    let contextMsg = text
    if (selection?.type === 'mail') {
      const m = selection.item
      contextMsg = `[Ausgewählte Mail]\nVon: ${m.sender}\nBetreff: ${m.subject}\nKategorie: ${m.kategorie}\n${m.zusammenfassung ? 'Zusammenfassung: ' + m.zusammenfassung + '\n' : ''}\n${text}`
    } else if (selection?.type === 'calendar') {
      const c = selection.item
      contextMsg = `[Ausgewählter Termin]\n"${c.subject}" am ${c.start?.slice(0, 10) ?? '?'}${c.location ? ', Ort: ' + c.location : ''}\n\n${text}`
    } else if (selection?.type === 'task') {
      const t = selection.item
      contextMsg = `[Ausgewählte Aufgabe]\n"${t.subject}", Priorität: ${t.priority}, Fällig: ${t.due_date ?? 'unbekannt'}\n\n${text}`
    }
    // Without specific selection: prepend mail overview as context
    if (!selection && mailSummary) {
      contextMsg = mailSummary + '\n\n' + contextMsg
    }

    let philText = ''
    setMessages((prev) => [...prev, { role: 'phil', text: '' }])

    try {
      // include_context=false: frontend already sends mail context from store
      const stream = api.chatStream(contextMsg, false)
      const reader = stream.getReader()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        philText += value
        setMessages((prev) => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'phil', text: philText }
          return updated
        })
      }
    } catch (e) {
      console.error(e)
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = { role: 'phil', text: 'Verbindungsfehler.' }
        return updated
      })
    } finally {
      setStreaming(false)
    }

    // TTS (optional)
    if (philText) {
      try {
        const url = await api.tts(philText.slice(0, 300))
        const audio = new Audio(url)
        audio.play()
        audio.onended = () => URL.revokeObjectURL(url)
      } catch { /* TTS optional */ }
    }
  }

  return (
    <div className={`${styles.panel} ${open ? styles.open : ''}`}>
      <div className={styles.header}>
        <img src="/phil.png" className={styles.avatar} alt="PHIL" />
        <div className={styles.headerText}>
          <span className={styles.headerTitle}>PHIL</span>
          {contextLabel && <span className={styles.contextLabel} title={contextLabel}>{contextLabel}</span>}
        </div>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Schließen">✕</button>
      </div>

      <div className={styles.quickActions}>
        {quickActions.map((action) => (
          <button key={action} className={styles.quickBtn} onClick={() => send(action)} disabled={streaming}>
            {action}
          </button>
        ))}
      </div>

      <div className={styles.messages}>
        {messages.length === 0 && (
          <p className={styles.emptyMsg}>
            {selection
              ? `Ich sehe den ausgewählten ${selection.type === 'mail' ? 'Mail' : selection.type === 'calendar' ? 'Termin' : 'Task'}. Was möchtest du wissen?`
              : 'Wähle ein Element aus oder stelle eine Frage.'}
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`${styles.msg} ${styles[msg.role]}`}>
            {msg.role === 'phil' && (
              <img src="/phil.png" className={styles.msgAvatar} alt="PHIL" />
            )}
            <div className={styles.msgBubble}>
              {msg.text || (streaming && i === messages.length - 1 ? '…' : '')}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className={styles.inputRow}>
        <input
          className={styles.input}
          placeholder="Frag PHIL…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send(input)
            }
          }}
          disabled={streaming}
        />
        <button
          className={styles.sendBtn}
          onClick={() => send(input)}
          disabled={!input.trim() || streaming}
          aria-label="Senden"
        >→</button>
      </div>
    </div>
  )
}
