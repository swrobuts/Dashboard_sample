import { useState, useCallback, useEffect, useMemo } from 'react'
import { useDataLoader } from '../../hooks/useDataLoader'
import { Calendar, dateFnsLocalizer, Navigate } from 'react-big-calendar'
import type { View, SlotInfo, ToolbarProps } from 'react-big-calendar'
import {
  format, parse, startOfWeek, getDay,
  startOfYear, eachMonthOfInterval, endOfYear,
  startOfMonth, endOfMonth, eachDayOfInterval,
  isToday, isSameDay, addYears, subYears,
  startOfDay, endOfDay,
} from 'date-fns'
import { de } from 'date-fns/locale'
import 'react-big-calendar/lib/css/react-big-calendar.css'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import type { CalendarItem } from '../../api/types'
import styles from './CalendarView.module.css'

// ── Localizer ────────────────────────────────────────────────────────────────
const localizer = dateFnsLocalizer({ format, parse, startOfWeek, getDay, locales: { de } })

const RBC_MESSAGES = {
  today: 'Heute', previous: '‹', next: '›', month: 'Monat',
  week: 'Woche', day: 'Tag', agenda: 'Agenda',
  date: 'Datum', time: 'Zeit', event: 'Ereignis',
  noEventsInRange: 'Keine Termine in diesem Zeitraum.',
  showMore: (n: number) => `+${n} weitere`,
}

// ── Types ────────────────────────────────────────────────────────────────────
type AppView = 'day' | 'week' | 'month' | 'year'

interface RbcEvent {
  id: string
  title: string
  start: Date
  end: Date
  resource: CalendarItem
}

interface FormState {
  subject: string; start: string; end: string; location: string; zoom_link: string; body: string
}

const DEFAULT_ZOOM = 'https://thws-de.zoom.us/j/4286927358'

// ── Helpers ──────────────────────────────────────────────────────────────────
function toRbcEvents(items: CalendarItem[]): RbcEvent[] {
  return items
    .filter((i) => i.start && i.end)
    .map((i) => ({
      id: i.id,
      title: i.subject,
      start: new Date(i.start!),
      end: new Date(i.end!),
      resource: i,
    }))
}

function toLocalDatetime(d: Date): string {
  return format(d, "yyyy-MM-dd'T'HH:mm")
}

/** "Büro | https://zoom.us/j/..." → { location: "Büro", zoom_link: "https://..." } */
function splitLocation(combined: string): { location: string; zoom_link: string } {
  if (!combined) return { location: '', zoom_link: '' }
  const match = combined.match(/^(.*?)\s*\|\s*(https?:\/\/.+)$/i)
  if (match) return { location: match[1].trim(), zoom_link: match[2].trim() }
  if (combined.match(/^https?:\/\//i)) return { location: '', zoom_link: combined }
  return { location: combined, zoom_link: '' }
}

// ── Custom RBC Toolbar (navigation only, no duplicate view buttons) ──────────
function RbcNavToolbar({ label, onNavigate }: ToolbarProps<RbcEvent>) {
  return (
    <div className={styles.rbcNav}>
      <button className={styles.navBtn} onClick={() => onNavigate(Navigate.PREVIOUS)}>‹</button>
      <button className={styles.rbcToday} onClick={() => onNavigate(Navigate.TODAY)}>Heute</button>
      <button className={styles.navBtn} onClick={() => onNavigate(Navigate.NEXT)}>›</button>
      <span className={styles.rbcLabel}>{label}</span>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────────────────
export function CalendarView() {
  const { calendar, setCalendar, removeCalendarItem, setSelection, loadingCalendar } = useStore()
  const { loadCalendar } = useDataLoader()
  const [view, setView] = useState<AppView>('month')
  const [date, setDate] = useState(new Date())
  const [saving, setSaving] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<FormState>({ subject: '', start: '', end: '', location: '', zoom_link: DEFAULT_ZOOM, body: '' })
  const [editEventId, setEditEventId] = useState<string | null>(null)  // null = create, string = edit
  const [activeEvent, setActiveEvent] = useState<RbcEvent | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [search, setSearch] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Fetch more data when switching to year view
  useEffect(() => {
    if (view === 'year') {
      setLoadingMore(true)
      api.calendar(400).then(({ items }) => setCalendar(items)).finally(() => setLoadingMore(false))
    }
  }, [view])

  const rbcEvents = useMemo(() => toRbcEvents(calendar), [calendar])

  const filteredEvents = useMemo(() => {
    if (!search) return rbcEvents
    const q = search.toLowerCase()
    return rbcEvents.filter((e) =>
      e.title.toLowerCase().includes(q) ||
      (e.resource.location ?? '').toLowerCase().includes(q)
    )
  }, [rbcEvents, search])

  // ── Open form helpers ───────────────────────────────────────────────────────
  function openForm(start?: Date, end?: Date) {
    const s = start ?? new Date()
    const e = end ?? new Date(s.getTime() + 60 * 60 * 1000)
    setForm({ subject: '', start: toLocalDatetime(s), end: toLocalDatetime(e), location: '', zoom_link: DEFAULT_ZOOM, body: '' })
    setEditEventId(null)
    setActiveEvent(null)
    setSaveError(null)
    setShowForm(true)
  }

  function closeForm() {
    setShowForm(false)
    setEditEventId(null)
    setSaveError(null)
    // Keep activeEvent so Phil panel retains context
  }

  // ── Create / Update ─────────────────────────────────────────────────────────
  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setSaveError(null)
    try {
      const combinedLocation = form.zoom_link
        ? (form.location ? `${form.location} | ${form.zoom_link}` : form.zoom_link)
        : form.location
      // Convert local datetime string to ISO (browser interprets "YYYY-MM-DDTHH:mm" as local time)
      const isoStart = new Date(form.start).toISOString()
      const isoEnd   = new Date(form.end).toISOString()

      if (editEventId) {
        await api.updateCalendar(editEventId, form.subject, form.start, form.end, combinedLocation, form.body)
        // Optimistic update: replace the existing event in the store immediately
        const updated: CalendarItem = {
          id: editEventId,
          changekey: activeEvent?.resource.changekey ?? '',
          subject: form.subject,
          start: isoStart,
          end: isoEnd,
          location: combinedLocation,
          body: form.body,
          is_recurring: false,
        }
        setCalendar(calendar.map((item) => item.id === editEventId ? updated : item))
      } else {
        const created = await api.createCalendar(form.subject, form.start, form.end, combinedLocation, form.body)
        // Optimistic insert: add the new event to the store immediately
        const newItem: CalendarItem = {
          id: created.id,
          changekey: '',
          subject: form.subject,
          start: isoStart,
          end: isoEnd,
          location: combinedLocation,
          body: form.body,
          is_recurring: false,
        }
        setCalendar([...calendar, newItem])
      }
      closeForm()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Speichern fehlgeschlagen.'
      setSaveError(msg)
    } finally {
      setSaving(false)
    }
  }

  // ── Delete (called from modal or directly) ──────────────────────────────────
  async function handleDeleteEvent(ev: RbcEvent) {
    setDeleting(true)
    try {
      await api.deleteCalendar(ev.resource.id, ev.resource.changekey)
    } catch (err) {
      console.error('[deleteCalendar]', err)
    } finally {
      removeCalendarItem(ev.resource.id)
      setActiveEvent(null)
      setShowForm(false)
      setEditEventId(null)
      setDeleting(false)
    }
  }

  // ── react-big-calendar callbacks ─────────────────────────────────────────────
  const handleSelectSlot = useCallback((slot: SlotInfo) => {
    openForm(slot.start, slot.end)
  }, [])

  const handleSelectEvent = useCallback((ev: RbcEvent) => {
    // Set Phil panel context
    setSelection({ type: 'calendar', item: ev.resource })
    // Open edit form with prefilled data
    const { location, zoom_link } = splitLocation(ev.resource.location ?? '')
    setForm({
      subject: ev.resource.subject,
      start: ev.resource.start ? toLocalDatetime(new Date(ev.resource.start)) : toLocalDatetime(new Date()),
      end: ev.resource.end ? toLocalDatetime(new Date(ev.resource.end)) : toLocalDatetime(new Date()),
      location,
      zoom_link,
      body: ev.resource.body ?? '',
    })
    setEditEventId(ev.resource.id)
    setActiveEvent(ev)
    setSaveError(null)
    setShowForm(true)
  }, [setSelection])

  const handleNavigate = useCallback((newDate: Date) => setDate(newDate), [])

  const handleViewChange = useCallback((v: View) => {
    setView(v as AppView)
  }, [])

  // ── Toolbar navigation for year view ─────────────────────────────────────
  function navYear(dir: -1 | 1) {
    setDate((d) => dir === 1 ? addYears(d, 1) : subYears(d, 1))
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className={styles.view}>
      {/* Row 1: search + sync + add */}
      <div className={styles.toolbar}>
        <input
          className={styles.search}
          type="search"
          placeholder="Termin suchen…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button
          className={styles.syncBtn}
          onClick={() => loadCalendar()}
          disabled={loadingCalendar}
          title="Kalender neu laden"
        >
          {loadingCalendar ? '…' : '↻'}
        </button>
        <button className={styles.addBtn} onClick={() => openForm()}>+ Neu</button>
      </div>

      {/* Row 2: view tabs */}
      <div className={styles.filterBar}>
        <div className={styles.viewTabs}>
          {(['day', 'week', 'month', 'year'] as AppView[]).map((v) => (
            <button
              key={v}
              className={`${styles.tabBtn} ${view === v ? styles.tabActive : ''}`}
              onClick={() => setView(v)}
            >
              {v === 'day' ? 'Tag' : v === 'week' ? 'Woche' : v === 'month' ? 'Monat' : 'Jahr'}
            </button>
          ))}
        </div>
      </div>

      {/* Create / Edit Modal */}
      {showForm && (
        <div className={styles.modalOverlay} onClick={(e) => e.target === e.currentTarget && closeForm()}>
          <form onSubmit={handleSave} className={styles.modal}>
            <div className={styles.modalHeader}>
              <h2 className={styles.modalTitle}>
                {editEventId ? 'Termin bearbeiten' : 'Neuer Termin'}
              </h2>
              <button type="button" className={styles.modalCloseBtn} onClick={closeForm} aria-label="Schließen">✕</button>
            </div>

            <input
              className={styles.input}
              placeholder="Titel *"
              value={form.subject}
              onChange={(e) => setForm({ ...form, subject: e.target.value })}
              required
              autoFocus
            />
            <div className={styles.row}>
              <div>
                <label className={styles.label}>Start</label>
                <input
                  className={styles.input}
                  type="datetime-local"
                  value={form.start}
                  onChange={(e) => setForm({ ...form, start: e.target.value })}
                  required
                />
              </div>
              <div>
                <label className={styles.label}>Ende</label>
                <input
                  className={styles.input}
                  type="datetime-local"
                  value={form.end}
                  onChange={(e) => setForm({ ...form, end: e.target.value })}
                  required
                />
              </div>
            </div>
            <input
              className={styles.input}
              placeholder="Ort (optional)"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
            <input
              className={styles.input}
              placeholder="Zoom-Link (optional)"
              value={form.zoom_link}
              onChange={(e) => setForm({ ...form, zoom_link: e.target.value })}
            />
            <textarea
              className={styles.textarea}
              placeholder="Notizen (optional)"
              rows={2}
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />

            {saveError && (
              <p className={styles.saveError}>{saveError}</p>
            )}

            <div className={styles.formActions}>
              {/* Delete button — left side, only in edit mode */}
              {editEventId && activeEvent && (
                <button
                  type="button"
                  className={styles.modalDeleteBtn}
                  onClick={() => handleDeleteEvent(activeEvent)}
                  disabled={deleting || saving}
                  title="Termin löschen"
                >
                  {deleting ? '…' : '🗑 Löschen'}
                </button>
              )}
              <div style={{ flex: 1 }} />
              <button type="button" className={styles.cancelBtn} onClick={closeForm}>
                Abbrechen
              </button>
              <button type="submit" className={styles.saveBtn} disabled={saving || deleting}>
                {saving ? '…' : editEventId ? 'Speichern' : 'Erstellen'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Calendar body */}
      <div className={styles.calBody}>
        {view === 'year' ? (
          <YearView
            date={date}
            events={filteredEvents}
            loading={loadingMore}
            onNavigate={navYear}
            onDayClick={(d) => openForm(startOfDay(d), endOfDay(d))}
            onEventClick={(ev) => {
              setSelection({ type: 'calendar', item: ev.resource })
              const { location, zoom_link } = splitLocation(ev.resource.location ?? '')
              setForm({
                subject: ev.resource.subject,
                start: ev.resource.start ? toLocalDatetime(new Date(ev.resource.start)) : toLocalDatetime(new Date()),
                end: ev.resource.end ? toLocalDatetime(new Date(ev.resource.end)) : toLocalDatetime(new Date()),
                location,
                zoom_link,
                body: ev.resource.body ?? '',
              })
              setEditEventId(ev.resource.id)
              setActiveEvent(ev)
              setSaveError(null)
              setShowForm(true)
            }}
          />
        ) : (
          <Calendar
            localizer={localizer}
            culture="de"
            events={filteredEvents}
            view={view as View}
            date={date}
            onNavigate={handleNavigate}
            onView={handleViewChange}
            onSelectSlot={handleSelectSlot}
            onSelectEvent={handleSelectEvent}
            selectable
            messages={RBC_MESSAGES}
            popup
            className={styles.rbc}
            components={{ toolbar: RbcNavToolbar }}
            formats={{
              timeGutterFormat: 'HH:mm',
              eventTimeRangeFormat: ({ start, end }) =>
                `${format(start, 'HH:mm')}–${format(end, 'HH:mm')}`,
              dayHeaderFormat: (d) => format(d, 'EEEE, d. MMMM', { locale: de }),
              dayRangeHeaderFormat: ({ start, end }) =>
                `${format(start, 'd. MMM', { locale: de })} – ${format(end, 'd. MMM yyyy', { locale: de })}`,
              monthHeaderFormat: (d) => format(d, 'MMMM yyyy', { locale: de }),
            }}
          />
        )}
      </div>
    </div>
  )
}

// ── Year View ─────────────────────────────────────────────────────────────────
interface YearViewProps {
  date: Date
  events: RbcEvent[]
  loading: boolean
  onNavigate: (dir: -1 | 1) => void
  onDayClick: (d: Date) => void
  onEventClick: (ev: RbcEvent) => void
}

function YearView({ date, events, loading, onNavigate, onDayClick, onEventClick }: YearViewProps) {
  const year = date.getFullYear()
  const months = eachMonthOfInterval({ start: startOfYear(date), end: endOfYear(date) })
  const DOW = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
  const [hoveredDay, setHoveredDay] = useState<Date | null>(null)

  function eventsForDay(d: Date) {
    return events.filter((ev) => isSameDay(ev.start, d))
  }

  return (
    <div className={styles.yearWrap}>
      <div className={styles.yearNav}>
        <button className={styles.navBtn} onClick={() => onNavigate(-1)}>‹</button>
        <span className={styles.yearTitle}>{year}</span>
        <button className={styles.navBtn} onClick={() => onNavigate(1)}>›</button>
        {loading && <span className={styles.yearLoading}>Lade…</span>}
      </div>
      <div className={styles.yearGrid}>
        {months.map((monthStart) => {
          const days = eachDayOfInterval({ start: startOfMonth(monthStart), end: endOfMonth(monthStart) })
          // Pad start: get day of week (Mon=0)
          const firstDow = (getDay(days[0]) + 6) % 7 // 0=Mon
          return (
            <div key={monthStart.toISOString()} className={styles.miniMonth}>
              <div className={styles.miniMonthName}>
                {format(monthStart, 'MMMM', { locale: de })}
              </div>
              <div className={styles.miniGrid}>
                {DOW.map((d) => <div key={d} className={styles.miniDow}>{d}</div>)}
                {Array.from({ length: firstDow }).map((_, i) => <div key={`pad-${i}`} />)}
                {days.map((d) => {
                  const dayEvents = eventsForDay(d)
                  const isHov = hoveredDay ? isSameDay(d, hoveredDay) : false
                  return (
                    <div
                      key={d.toISOString()}
                      className={`${styles.miniDay}
                        ${isToday(d) ? styles.miniToday : ''}
                        ${dayEvents.length > 0 ? styles.miniHasEvent : ''}
                        ${isHov ? styles.miniHover : ''}`}
                      title={dayEvents.map((e) => e.title).join('\n') || undefined}
                      onMouseEnter={() => setHoveredDay(d)}
                      onMouseLeave={() => setHoveredDay(null)}
                      onClick={() => {
                        if (dayEvents.length > 0) onEventClick(dayEvents[0])
                        else onDayClick(d)
                      }}
                    >
                      <span className={styles.miniDayNum}>{d.getDate()}</span>
                      {dayEvents.length > 0 && (
                        <span className={styles.miniDot} style={dayEvents.length > 1 ? { background: 'var(--amber)' } : undefined} />
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
