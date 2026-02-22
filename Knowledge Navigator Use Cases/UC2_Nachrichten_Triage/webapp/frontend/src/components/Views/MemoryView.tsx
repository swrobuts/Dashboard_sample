import { useState, useEffect, useCallback } from 'react'
import { api } from '../../api/client'
import type { MemoryFact } from '../../api/types'
import styles from './MemoryView.module.css'

const CATEGORIES = ['Alle', 'Person', 'Projekt', 'Konzept', 'Prozedur', 'Ort']

export function MemoryView() {
  const [facts, setFacts] = useState<MemoryFact[]>([])
  const [loading, setLoading] = useState(true)
  const [categoryFilter, setCategoryFilter] = useState('Alle')
  const [minConfidence, setMinConfidence] = useState(0)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Parameters<typeof api.memoryFacts>[0] = {}
      if (categoryFilter !== 'Alle') params.category = categoryFilter
      if (minConfidence > 0) params.min_confidence = minConfidence / 100
      const { facts: data } = await api.memoryFacts(params)
      setFacts(data)
    } catch { /* silent */ }
    finally { setLoading(false) }
  }, [categoryFilter, minConfidence])

  useEffect(() => { load() }, [load])

  async function handleDelete(id: string) {
    await api.memoryDeleteFact(id)
    setFacts((prev) => prev.filter((f) => f.id !== id))
  }

  async function handleSaveEdit(id: string) {
    await api.memoryUpdateFact(id, editText, 'Manuell korrigiert')
    setFacts((prev) => prev.map((f) => f.id === id ? { ...f, text: editText } : f))
    setEditingId(null)
  }

  function startEdit(fact: MemoryFact) {
    setEditingId(fact.id)
    setEditText(fact.text)
  }

  function confidenceColor(c: number) {
    if (c >= 0.75) return '#059669'
    if (c >= 0.5)  return '#D97706'
    return '#DC2626'
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>🧠 Phil's Gedächtnis</h2>
        <span className={styles.count}>{facts.length} Fakten</span>
        <button className={styles.refreshBtn} onClick={load} disabled={loading}>↺</button>
      </div>

      <div className={styles.filters}>
        <div className={styles.categoryChips}>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              className={`${styles.chip} ${categoryFilter === cat ? styles.chipActive : ''}`}
              onClick={() => setCategoryFilter(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
        <label className={styles.confidenceLabel}>
          Min. Konfidenz: {minConfidence}%
          <input
            type="range" min={0} max={90} step={10}
            value={minConfidence}
            onChange={(e) => setMinConfidence(Number(e.target.value))}
            className={styles.slider}
          />
        </label>
      </div>

      {loading && <div className={styles.empty}>Lade…</div>}
      {!loading && facts.length === 0 && (
        <div className={styles.empty}>Noch keine Fakten gespeichert.</div>
      )}

      {!loading && facts.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Fakt</th>
                <th>Kategorie</th>
                <th>Quelle</th>
                <th>Konfidenz</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {facts.map((f) => (
                <tr key={f.id}>
                  <td className={styles.textCell}>
                    {editingId === f.id ? (
                      <input
                        className={styles.editInput}
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveEdit(f.id)
                          if (e.key === 'Escape') setEditingId(null)
                        }}
                        autoFocus
                      />
                    ) : (
                      <span title={f.correction_note ?? undefined}>{f.text}</span>
                    )}
                  </td>
                  <td><span className={styles.categoryBadge}>{f.category}</span></td>
                  <td className={styles.sourceCell}>
                    <span className={styles.sourceBadge} data-source={f.source}>{f.source}</span>
                    {f.source_ref && <span className={styles.sourceRef} title={f.source_ref}>…</span>}
                  </td>
                  <td>
                    <div className={styles.confBar}>
                      <div className={styles.confBarTrack}>
                        <div
                          className={styles.confFill}
                          style={{
                            width: `${Math.round(f.confidence * 100)}%`,
                            background: confidenceColor(f.confidence),
                          }}
                        />
                      </div>
                      <span className={styles.confLabel}>{Math.round(f.confidence * 100)}%</span>
                    </div>
                  </td>
                  <td className={styles.actionsCell}>
                    {editingId === f.id ? (
                      <>
                        <button className={styles.actionBtn} onClick={() => handleSaveEdit(f.id)} title="Speichern">✓</button>
                        <button className={styles.actionBtn} onClick={() => setEditingId(null)} title="Abbrechen">✕</button>
                      </>
                    ) : (
                      <>
                        <button className={styles.actionBtn} onClick={() => startEdit(f)} title="Bearbeiten">✏</button>
                        <button className={`${styles.actionBtn} ${styles.deleteBtn}`} onClick={() => handleDelete(f.id)} title="Löschen">🗑</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
