import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
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
  const comma = raw.match(/^([^,]+),\s*(.+)$/)
  return comma ? `${comma[2].trim()} ${comma[1].trim()}` : raw
}

/** "THWS | Austausch mit Kai Hufnagel" → "Kai Hufnagel" */
function extractPersonFromSubject(subject: string): string | null {
  const m = subject.match(/\bmit\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)+)/i)
  return m ? m[1] : null
}

// ── Sub-components ──────────────────────────────────────────────────────────

function RagBlock({ results }: { results: KnowledgeResult[] }) {
  if (!results.length) return null
  return (
    <details className={styles.sourceDetails}>
      <summary className={styles.sourcesSummary}>
        📚 {results.length} ähnliche Mail{results.length > 1 ? 's' : ''} gefunden
      </summary>
      <div className={styles.ragList}>
        {results.map((r) => (
          <div key={r.id} className={styles.ragItem}>
            <span className={`${styles.ragScore} ${r.score >= 0.85 ? styles.ragScoreHigh : ''}`}>
              {Math.round(r.score * 100)}%
            </span>
            <div className={styles.ragMeta}>
              <span className={styles.ragSubject}>{r.subject}</span>
              <span className={styles.ragSender}>{r.sender} · {r.date}</span>
              {r.summary && <span className={styles.ragSummaryText}>{r.summary}</span>}
            </div>
          </div>
        ))}
      </div>
    </details>
  )
}

function InlineGraphBlock({ data, loading }: { data: GraphData | null; loading: boolean }) {
  const [open, setOpen] = useState(false)

  if (loading) return (
    <div className={styles.sourceDetails}>
      <div className={styles.sourcesSummary} style={{ cursor: 'default' }}>
        <span className={styles.typingDot}>⏳</span> Wissensgraph wird berechnet…
      </div>
    </div>
  )
  if (!data || data.nodes.length <= 1) return null

  const entityCount = data.nodes.filter((n) => n.id !== 'center').length

  return (
    <>
      <button className={styles.graphTriggerBtn} onClick={() => setOpen(true)}>
        🕸 Wissensgraph · {entityCount} Entität{entityCount !== 1 ? 'en' : ''} — anzeigen
      </button>

      {open && createPortal(
        <div className={styles.graphPopoverOverlay} onClick={() => setOpen(false)}>
          <div className={styles.graphPopoverDialog} onClick={(e) => e.stopPropagation()}>
            <div className={styles.graphPopoverHeader}>
              <span className={styles.graphPopoverTitle}>🕸 Wissensgraph</span>
              <button className={styles.graphPopoverClose} onClick={() => setOpen(false)} aria-label="Schließen">✕</button>
            </div>
            <div className={styles.graphPopoverBody}>
              <PhilGraph data={data} />
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  )
}

// ── Main Component ──────────────────────────────────────────────────────────

export function PhilPanel({ open, onClose }: Props) {
  const { selection, setView, setTrainPreset } = useStore()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loadingGraph, setLoadingGraph] = useState(false)
  const [ragResults, setRagResults] = useState<KnowledgeResult[]>([])
  const [mailGraphData, setMailGraphData] = useState<GraphData | null>(null)
  const [mailGraphLoading, setMailGraphLoading] = useState(false)

  const [ttsIdx, setTtsIdx] = useState<number | null>(null)
  const [ttsLoadingIdx, setTtsLoadingIdx] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Only show RAG results above relevance threshold
  const filteredRag = ragResults.filter((r) => r.score >= 0.70)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
    if (ttsIdx === idx && audioRef.current) {
      audioRef.current.pause()
      setTtsIdx(null)
      return
    }
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

  const linkedinName: string | null =
    selection?.type === 'mail' ? parseSenderName(selection.item.sender) :
    selection?.type === 'calendar' ? extractPersonFromSubject(selection.item.subject) :
    null
  const linkedinUrl = linkedinName
    ? `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(linkedinName)}`
    : null

  const trainLocation: string | null =
    selection?.type === 'calendar' && selection.item.location &&
    !selection.item.location.match(/^https?:\/\//i)
      ? selection.item.location : null

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
    setRagResults([])
    setMailGraphData(null)

    // RAG: query by the selected item's content so results are actually related,
    // not by the user's typed message (which is often a generic action like "Zusammenfassen")
    const ragQuery = selection?.type === 'mail'
      ? `${selection.item.subject} ${selection.item.zusammenfassung ?? ''}`.trim()
      : selection?.type === 'calendar'
      ? selection.item.subject
      : selection?.type === 'task'
      ? selection.item.subject
      : text
    api.knowledgeSearch(ragQuery, 5)
      .then(({ results }) => setRagResults(results))
      .catch(() => {})

    // Graph: auto-fetch from selected mail's content so it shows relevant entities
    if (selection?.type === 'mail') {
      const m = selection.item
      setMailGraphLoading(true)
      api.graph(m.subject, `Von: ${m.sender}\nBetreff: ${m.subject}\n${m.body ?? m.zusammenfassung ?? ''}`)
        .then((data) => setMailGraphData(data))
        .catch(() => {})
        .finally(() => setMailGraphLoading(false))
    }
    setMessages((prev) => [...prev, { role: 'user', text }])
    setStreaming(true)
    stopAudio()

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

  // Last index of a Phil message (for inline sources)
  const lastPhilIdx = messages.reduce((acc, m, i) => m.role === 'phil' ? i : acc, -1)

  return (
    <div className={`${styles.panel} ${open ? styles.open : ''}`}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className={styles.header}>
        <div className={styles.avatarRow}>
          <img src="/phil.png" alt="PHIL" className={styles.avatar} />
          <div className={styles.avatarName}>PHIL</div>
          {contextLabel && <span className={styles.contextLabel} title={contextLabel}>{contextLabel}</span>}
        </div>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Schließen">✕</button>
      </div>

      {/* ── Quick Actions ──────────────────────────────────────────────────── */}
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

      {/* ── Graph overlay ──────────────────────────────────────────────────── */}
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

      {/* ── Messages ───────────────────────────────────────────────────────── */}
      <div className={styles.messages}>
        {messages.length === 0 && (
          <p className={styles.emptyMsg}>
            {selection
              ? `Ich sehe den ausgewählten ${selection.type === 'mail' ? 'Mail' : selection.type === 'calendar' ? 'Termin' : 'Task'}. Was möchtest du wissen?`
              : 'Wähle ein Element aus oder stelle eine Frage.'}
          </p>
        )}

        {messages.map((msg, i) => (
          <div key={i}>
            <div className={`${styles.msg} ${styles[msg.role]}`}>
              {msg.role === 'phil' && (
                <img src="/phil.png" className={styles.msgAvatar} alt="PHIL" />
              )}
              <div className={`${styles.msgBubble} ${msg.role === 'phil' ? styles.msgBubbleMd : ''}`}>
                {msg.role === 'phil'
                  ? msg.text
                    ? <ReactMarkdown>{msg.text}</ReactMarkdown>
                    : (streaming && i === messages.length - 1 ? <span className={styles.typingDot}>…</span> : null)
                  : msg.text}
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

            {/* Inline sources — shown below the last Phil response only */}
            {msg.role === 'phil' && i === lastPhilIdx && !streaming && (
              <div className={styles.sourcesBlock}>
                <RagBlock results={filteredRag} />
                <InlineGraphBlock data={mailGraphData} loading={mailGraphLoading} />
              </div>
            )}
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Input ──────────────────────────────────────────────────────────── */}
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
