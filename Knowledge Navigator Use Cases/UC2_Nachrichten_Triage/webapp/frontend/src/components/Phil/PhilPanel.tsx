import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import { PhilGraph } from './PhilGraph'
import type { GraphData } from './PhilGraph'
import type { KnowledgeResult } from '../../api/types'
import styles from './PhilPanel.module.css'

interface ChatMessage { role: 'user' | 'phil'; text: string }

interface Props { open: boolean; onClose: () => void }

// ── Helpers ────────────────────────────────────────────────────────────────

/** "\"Hufnagel, Kai\" <kai@thws.de>" → "Kai Hufnagel" */
function parseSenderName(sender: string): string | null {
  const m = sender.match(/^["']?([^<"'\n]+?)["']?\s*</)
  if (!m) return null
  const raw = m[1].trim()
  // "Last, First" → "First Last"
  const comma = raw.match(/^([^,]+),\s*(.+)$/)
  return comma ? `${comma[2].trim()} ${comma[1].trim()}` : raw
}

/** "THWS | Austausch mit Kai Hufnagel" → "Kai Hufnagel" */
function extractPersonFromSubject(subject: string): string | null {
  const m = subject.match(/\bmit\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)+)/i)
  return m ? m[1] : null
}

export function PhilPanel({ open, onClose }: Props) {
  const { selection, setView, setTrainPreset } = useStore()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loadingGraph, setLoadingGraph] = useState(false)
  const [ragResults, setRagResults] = useState<KnowledgeResult[]>([])

  // Per-message TTS state
  const [ttsIdx, setTtsIdx] = useState<number | null>(null)       // which message is playing
  const [ttsLoadingIdx, setTtsLoadingIdx] = useState<number | null>(null) // which is loading
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Clean up audio on unmount
  useEffect(() => {
    return () => {
      audioRef.current?.pause()
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
    }
  }, [])

  function stopAudio() {
    audioRef.current?.pause()
    audioRef.current = null
    if (audioUrlRef.current) { URL.revokeObjectURL(audioUrlRef.current); audioUrlRef.current = null }
    setTtsIdx(null)
  }

  async function toggleTts(text: string, idx: number) {
    // Pause if this message is already playing
    if (ttsIdx === idx && audioRef.current) {
      audioRef.current.pause()
      setTtsIdx(null)
      return
    }

    // Stop any current audio
    stopAudio()

    setTtsLoadingIdx(idx)
    try {
      const url = await api.tts(text.slice(0, 500))
      audioUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onplay = () => { setTtsIdx(idx); setTtsLoadingIdx(null) }
      audio.onpause = () => setTtsIdx(null)
      audio.onended = () => {
        setTtsIdx(null)
        URL.revokeObjectURL(url)
        audioUrlRef.current = null
        audioRef.current = null
      }
      audio.play()
    } catch {
      setTtsLoadingIdx(null)
    }
  }

  const contextLabel = selection
    ? selection.type === 'mail'
      ? `Mail: "${selection.item.subject.slice(0, 50)}"`
      : selection.type === 'calendar'
      ? `Termin: "${selection.item.subject.slice(0, 50)}"`
      : `Aufgabe: "${selection.item.subject.slice(0, 50)}"`
    : null

  const quickActions: string[] = selection?.type === 'mail'
    ? ['Zusammenfassen', 'Antwort formulieren', 'Priorität begründen', 'Nächste Schritte', 'Als Aufgabe anlegen']
    : selection?.type === 'calendar'
    ? ['Vorbereitung checken', 'Agenda vorschlagen', 'Konflikt prüfen', 'Nachbereitung planen', 'Teilnehmer informieren']
    : selection?.type === 'task'
    ? ['Aufgabe beschreiben', 'Aufwand schätzen', 'Unteraufgaben vorschlagen', 'Dringlichkeit prüfen', 'E-Mail entwerfen']
    : ['Was steht heute an?', 'Wichtigste Aufgaben', 'Freie Slots finden', 'Wochenvorschau', 'Überfällige Aufgaben']

  // LinkedIn pill — derived from sender (mail) or subject person (calendar)
  const linkedinName: string | null =
    selection?.type === 'mail' ? parseSenderName(selection.item.sender) :
    selection?.type === 'calendar' ? extractPersonFromSubject(selection.item.subject) :
    null
  const linkedinUrl = linkedinName
    ? `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(linkedinName)}`
    : null

  // Train quick action — calendar events with a location
  const trainLocation: string | null =
    selection?.type === 'calendar' && selection.item.location ? selection.item.location : null

  // Calendar thread action
  const calendarPerson: string | null =
    selection?.type === 'calendar' ? extractPersonFromSubject(selection.item.subject) : null
  const calendarThreadAction = calendarPerson
    ? `Zeige mir alle meine Termine mit ${calendarPerson} in chronologischer Reihenfolge.`
    : null

  async function showGraph() {
    if (!selection) return
    setLoadingGraph(true)
    setGraphData(null)
    try {
      let subject = '', text = ''
      if (selection.type === 'mail') {
        subject = selection.item.subject
        text = `Von: ${selection.item.sender}\nBetreff: ${selection.item.subject}\n${selection.item.body ?? ''}`
      } else if (selection.type === 'calendar') {
        subject = selection.item.subject
        text = `Termin: ${selection.item.subject}\nStart: ${selection.item.start ?? ''}\nOrt: ${selection.item.location ?? ''}\n${selection.item.body ?? ''}`
      } else if (selection.type === 'task') {
        subject = selection.item.subject
        text = `Aufgabe: ${selection.item.subject}\nFällig: ${selection.item.due_date ?? ''}\nPriorität: ${selection.item.priority}\n${selection.item.body ?? ''}`
      }
      const data = await api.graph(subject, text)
      setGraphData(data)
    } catch (e) { console.error(e) }
    finally { setLoadingGraph(false) }
  }

  async function send(text: string) {
    if (!text.trim() || streaming) return
    setInput('')
    // Fetch RAG sources in parallel (non-blocking — don't await)
    setRagResults([])
    api.knowledgeSearch(text, 3)
      .then(({ results }) => setRagResults(results))
      .catch(() => {})
    setMessages((prev) => [...prev, { role: 'user', text }])
    setStreaming(true)
    stopAudio()

    // Prepend selection-specific context if an item is selected
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

    let philText = ''
    setMessages((prev) => [...prev, { role: 'phil', text: '' }])

    try {
      // include_context=true → backend fetches mails + Google Calendar + EWS tasks
      const stream = api.chatStream(contextMsg, true)
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
      const errText = e instanceof Error ? e.message : 'Verbindungsfehler.'
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = { role: 'phil', text: errText }
        return updated
      })
    } finally {
      setStreaming(false)
      // Guard: if stream ended with no data and no exception caught (shouldn't happen but safety net)
      setMessages((prev) => {
        if (prev.length > 0 && prev[prev.length - 1].role === 'phil' && prev[prev.length - 1].text === '') {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'phil', text: 'Keine Antwort erhalten.' }
          return updated
        }
        return prev
      })
    }
  }

  return (
    <div className={`${styles.panel} ${open ? styles.open : ''}`}>
      <div className={styles.header}>
        <img src="/phil.png" className={styles.avatar} alt="PHIL" />
        <div className={styles.headerText}>
          <div className={styles.headerTitleRow}>
            <span className={styles.headerTitle}>PHIL</span>
          </div>
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
        {calendarThreadAction && (
          <button
            className={`${styles.quickBtn} ${styles.quickBtnCalThread}`}
            onClick={() => send(calendarThreadAction)}
            disabled={streaming}
            title="Alle Termine mit dieser Person anzeigen"
          >
            🗓 Terminverlauf
          </button>
        )}
        {trainLocation && (
          <button
            className={`${styles.quickBtn} ${styles.quickBtnTrain}`}
            onClick={() => { setTrainPreset({ to: trainLocation }); setView('trains'); onClose() }}
            title={`Zugverbindung nach ${trainLocation} suchen`}
          >
            🚄 Zug nach {trainLocation.split(',')[0]}
          </button>
        )}
        {linkedinUrl && (
          <a
            href={linkedinUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={`${styles.quickBtn} ${styles.quickBtnLinkedIn}`}
            title={`${linkedinName} auf LinkedIn suchen`}
          >
            in LinkedIn
          </a>
        )}
        {selection && (
          <button
            className={`${styles.quickBtn} ${styles.quickBtnGraph}`}
            onClick={showGraph}
            disabled={loadingGraph || streaming}
            title="Als Wissensgraph darstellen"
          >
            {loadingGraph ? '⏳' : '🕸 Graph'}
          </button>
        )}
      </div>

      {/* Graph popover — rendered as fixed overlay outside the panel flow */}
      {graphData && (
        <div className={styles.graphOverlay} onClick={() => setGraphData(null)}>
          <div className={styles.graphDialog} onClick={(e) => e.stopPropagation()}>
            <div className={styles.graphDialogHeader}>
              <span className={styles.graphDialogTitle}>Wissensgraph</span>
              <button className={styles.closeBtn} onClick={() => setGraphData(null)} aria-label="Schließen">✕</button>
            </div>
            <div className={styles.graphDialogBody}>
              <PhilGraph data={graphData} />
            </div>
          </div>
        </div>
      )}

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
            <div className={`${styles.msgBubble} ${msg.role === 'phil' ? styles.msgBubbleMd : ''}`}>
              {msg.role === 'phil'
                ? msg.text
                  ? <ReactMarkdown>{msg.text}</ReactMarkdown>
                  : (streaming && i === messages.length - 1 ? <span className={styles.typingDot}>…</span> : null)
                : msg.text}
              {/* TTS button on completed Phil messages */}
              {msg.role === 'phil' && msg.text && !(streaming && i === messages.length - 1) && (
                <button
                  className={`${styles.msgTtsBtn} ${ttsIdx === i ? styles.msgTtsBtnPlaying : ''}`}
                  onClick={() => toggleTts(msg.text, i)}
                  disabled={ttsLoadingIdx === i}
                  title={ttsIdx === i ? 'Pause' : 'Vorlesen'}
                  aria-label={ttsIdx === i ? 'Pause' : 'Vorlesen'}
                >
                  {ttsLoadingIdx === i ? '…' : ttsIdx === i ? '⏸' : '▶'}
                </button>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {ragResults.length > 0 && (
        <details className={styles.ragSources}>
          <summary className={styles.ragSummary}>
            📚 {ragResults.length} ähnliche frühere Mail{ragResults.length > 1 ? 's' : ''} gefunden
          </summary>
          {ragResults.map((r) => (
            <div key={r.id} className={styles.ragItem}>
              <span className={styles.ragScore}>{Math.round(r.score * 100)}%</span>
              <div className={styles.ragMeta}>
                <span className={styles.ragSubject}>{r.subject}</span>
                <span className={styles.ragSender}>{r.sender} · {r.date}</span>
                <span className={styles.ragSummaryText}>{r.summary}</span>
              </div>
            </div>
          ))}
        </details>
      )}

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
