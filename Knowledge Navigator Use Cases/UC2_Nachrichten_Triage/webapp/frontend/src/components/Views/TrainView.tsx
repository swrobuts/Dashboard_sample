import { useState, useRef, useEffect, useCallback } from 'react'
import { api } from '../../api/client'
import { useStore } from '../../store/useStore'
import type { TrainStation, TrainJourney } from '../../api/types'
import styles from './TrainView.module.css'

export function TrainView() {
  const { trainPreset, setTrainPreset } = useStore()

  const [fromQuery, setFromQuery] = useState('')
  const [toQuery, setToQuery] = useState('')
  const [fromStation, setFromStation] = useState<TrainStation | null>(null)
  const [toStation, setToStation] = useState<TrainStation | null>(null)
  const [fromSuggestions, setFromSuggestions] = useState<TrainStation[]>([])
  const [toSuggestions, setToSuggestions] = useState<TrainStation[]>([])
  const [departure, setDeparture] = useState('')
  const [journeys, setJourneys] = useState<TrainJourney[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fromTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const toTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fromContainerRef = useRef<HTMLDivElement>(null)
  const toContainerRef = useRef<HTMLDivElement>(null)

  // Only clear suggestions when focus leaves the whole autocomplete container
  const onFromContainerBlur = useCallback((e: React.FocusEvent) => {
    if (!fromContainerRef.current?.contains(e.relatedTarget as Node)) {
      setFromSuggestions([])
    }
  }, [])
  const onToContainerBlur = useCallback((e: React.FocusEvent) => {
    if (!toContainerRef.current?.contains(e.relatedTarget as Node)) {
      setToSuggestions([])
    }
  }, [])

  // Apply preset from Phil (calendar event location)
  useEffect(() => {
    if (trainPreset) {
      setToQuery(trainPreset.to)
      setTrainPreset(null)
      // Auto-search station name
      api.trainStations(trainPreset.to).then(({ stations }) => {
        if (stations.length > 0) { setToStation(stations[0]); setToQuery(stations[0].name) }
      }).catch(() => {})
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function fetchSuggestions(query: string, which: 'from' | 'to') {
    if (query.length < 2) return
    try {
      const { stations } = await api.trainStations(query)
      if (which === 'from') setFromSuggestions(stations)
      else setToSuggestions(stations)
    } catch {}
  }

  function onFromChange(v: string) {
    setFromQuery(v); setFromStation(null)
    if (fromTimer.current) clearTimeout(fromTimer.current)
    fromTimer.current = setTimeout(() => fetchSuggestions(v, 'from'), 300)
  }

  function onToChange(v: string) {
    setToQuery(v); setToStation(null)
    if (toTimer.current) clearTimeout(toTimer.current)
    toTimer.current = setTimeout(() => fetchSuggestions(v, 'to'), 300)
  }

  function selectFrom(s: TrainStation) {
    setFromStation(s); setFromQuery(s.name); setFromSuggestions([])
  }
  function selectTo(s: TrainStation) {
    setToStation(s); setToQuery(s.name); setToSuggestions([])
  }

  function swapStations() {
    const [tmpS, tmpQ] = [fromStation, fromQuery]
    setFromStation(toStation); setFromQuery(toQuery)
    setToStation(tmpS); setToQuery(tmpQ)
  }

  function bahnDeUrl() {
    const from = encodeURIComponent(fromQuery.trim())
    const to = encodeURIComponent(toQuery.trim())
    let dateStr = ''
    if (departure) {
      const d = new Date(departure)
      const dd = String(d.getDate()).padStart(2, '0')
      const mm = String(d.getMonth() + 1).padStart(2, '0')
      const yy = String(d.getFullYear()).slice(2)
      const hh = String(d.getHours()).padStart(2, '0')
      const min = String(d.getMinutes()).padStart(2, '0')
      dateStr = `;D=${dd}.${mm}.${yy};T=${hh}${min}00`
    }
    return `https://www.bahn.de/buchung/start#ot=1&sucheNachVerbindung;S=${from};Z=${to}${dateStr};etyp=0;kl=2;rtype=classic`
  }

  const canSearch = fromQuery.trim().length >= 2 && toQuery.trim().length >= 2

  async function search() {
    if (!canSearch) return
    setLoading(true); setError(null)
    try {
      // Auto-resolve station if user typed but didn't click a suggestion
      let from = fromStation
      let to = toStation
      if (!from) {
        const { stations } = await api.trainStations(fromQuery.trim())
        if (!stations.length) { setError('Abfahrtsbahnhof nicht gefunden.'); setLoading(false); return }
        from = stations[0]; setFromStation(from); setFromQuery(from.name)
      }
      if (!to) {
        const { stations } = await api.trainStations(toQuery.trim())
        if (!stations.length) { setError('Zielbahnhof nicht gefunden.'); setLoading(false); return }
        to = stations[0]; setToStation(to); setToQuery(to.name)
      }
      const when = departure ? new Date(departure).toISOString() : undefined
      const { journeys: results } = await api.trainJourneys(from.id, to.id, when)
      setJourneys(results)
      if (results.length === 0) setError('Keine Verbindungen gefunden.')
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Verbindungsfehler'
      setError(`API nicht erreichbar: ${msg}`)
    } finally { setLoading(false) }
  }

  function fmtTime(iso: string | null) {
    if (!iso) return '—'
    return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
  }

  function fmtDur(dep: string | null, arr: string | null) {
    if (!dep || !arr) return ''
    const mins = Math.round((new Date(arr).getTime() - new Date(dep).getTime()) / 60000)
    const h = Math.floor(mins / 60), m = mins % 60
    return h > 0 ? `${h}h ${m > 0 ? m + 'min' : ''}`.trim() : `${m} min`
  }

  return (
    <div className={styles.view}>
      {/* Search card */}
      <div className={styles.searchCard}>
        <div className={styles.stationRow}>
          {/* From */}
          <div className={styles.stationField}>
            <label className={styles.label}>Von</label>
            <div className={styles.autocomplete} ref={fromContainerRef} onBlur={onFromContainerBlur}>
              <input
                className={`${styles.input} ${fromStation ? styles.inputSelected : ''}`}
                value={fromQuery}
                onChange={(e) => onFromChange(e.target.value)}
                placeholder="Abfahrtsbahnhof…"
              />
              {fromSuggestions.length > 0 && (
                <div className={styles.suggestions}>
                  {fromSuggestions.map((s) => (
                    <button key={s.id} className={styles.suggestion} tabIndex={0} onClick={() => selectFrom(s)}>
                      {s.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <button className={styles.swapBtn} onClick={swapStations} title="Tauschen">⇄</button>

          {/* To */}
          <div className={styles.stationField}>
            <label className={styles.label}>Nach</label>
            <div className={styles.autocomplete} ref={toContainerRef} onBlur={onToContainerBlur}>
              <input
                className={`${styles.input} ${toStation ? styles.inputSelected : ''}`}
                value={toQuery}
                onChange={(e) => onToChange(e.target.value)}
                placeholder="Zielbahnhof…"
              />
              {toSuggestions.length > 0 && (
                <div className={styles.suggestions}>
                  {toSuggestions.map((s) => (
                    <button key={s.id} className={styles.suggestion} tabIndex={0} onClick={() => selectTo(s)}>
                      {s.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className={styles.timeRow}>
          <div className={styles.stationField}>
            <label className={styles.label}>Abfahrt</label>
            <input
              type="datetime-local"
              className={styles.input}
              value={departure}
              onChange={(e) => setDeparture(e.target.value)}
            />
          </div>
          <button
            className={styles.searchBtn}
            onClick={search}
            disabled={!canSearch || loading}
          >
            {loading ? '⏳ Suche…' : '🔍 Verbindungen'}
          </button>
          {canSearch && (
            <a
              className={styles.bahnLink}
              href={bahnDeUrl()}
              target="_blank"
              rel="noopener noreferrer"
              title="Auf bahn.de öffnen"
            >
              🌐 bahn.de
            </a>
          )}
        </div>
      </div>

      {/* Results */}
      {error && (
        <div className={styles.errorBox}>
          <p className={styles.error}>{error}</p>
          {canSearch && (
            <a className={styles.bahnLinkBlock} href={bahnDeUrl()} target="_blank" rel="noopener noreferrer">
              🌐 Stattdessen auf bahn.de suchen
            </a>
          )}
        </div>
      )}

      {journeys.length > 0 && (
        <div className={styles.results}>
          {journeys.map((j, i) => (
            <div key={i} className={styles.journey}>
              <div className={styles.journeyTimes}>
                <div className={styles.timeBlock}>
                  <span className={styles.time}>{fmtTime(j.departure)}</span>
                  {j.delay_dep > 0 && <span className={styles.delay}>+{j.delay_dep}'</span>}
                  <span className={styles.station}>{fromStation?.name.split(' ')[0]}</span>
                </div>

                <div className={styles.journeyMiddle}>
                  <span className={styles.dur}>{fmtDur(j.departure, j.arrival)}</span>
                  <div className={styles.bar}>
                    <div className={styles.barLine} />
                    {Array.from({ length: j.changes }).map((_, ci) => (
                      <div key={ci} className={styles.barDot} style={{ left: `${((ci + 1) / (j.changes + 1)) * 100}%` }} />
                    ))}
                  </div>
                  <span className={styles.changes}>
                    {j.changes === 0 ? 'Direkt' : `${j.changes}× umsteigen`}
                  </span>
                </div>

                <div className={styles.timeBlock}>
                  <span className={styles.time}>{fmtTime(j.arrival)}</span>
                  {j.delay_arr > 0 && <span className={styles.delay}>+{j.delay_arr}'</span>}
                  <span className={styles.station}>{toStation?.name.split(' ')[0]}</span>
                </div>
              </div>

              <div className={styles.journeyMeta}>
                <span className={styles.products}>{j.products.join(' › ')}</span>
                {j.price !== null && (
                  <span className={styles.price}>ab {j.price.toFixed(2)} €</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {journeys.length === 0 && !loading && !error && (
        <div className={styles.empty}>
          <p>Bahnhöfe auswählen und auf <strong>Verbindungen</strong> klicken.</p>
          <p className={styles.emptyHint}>Tipp: Bei Kalenderterminen mit Ort bietet Phil einen direkten 🚄-Schnellzugriff an.</p>
        </div>
      )}
    </div>
  )
}
