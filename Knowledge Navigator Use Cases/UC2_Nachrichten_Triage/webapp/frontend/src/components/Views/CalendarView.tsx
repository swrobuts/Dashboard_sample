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
  const [loadingMore, setLoadingMore] = useState(false)
  const [search, setSearch] = useState('')
  const [activeEvent, setActiveEvent] = useState<RbcEvent | null>(null)
  const [deleting, setDeleting] = useState(false)

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

  // ── Create form ────────────────────────────────────────────────────────────
  function openForm(start?: Date, end?: Date) {
    const s = start ?? new Date()
    const e = end ?? new Date(s.getTime() + 60 * 60 * 1000)
    setForm({ subject: '', start: toLocalDatetime(s), end: toLocalDatetime(e), location: '', zoom_link: DEFAULT_ZOOM, body: '' })
    setShowForm(true)
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      // Zoom-Link in Location einbetten (Google Calendar zeigt es als Ort)
      const combinedLocation = form.zoom_link
        ? (form.location ? `${form.location} | ${form.zoom_link}` : form.zoom_link)
        : form.location
      await api.createCalendar(form.subject, form.start, form.end, combinedLocation, form.body)
      const daysAhead = view === 'year' ? 400 : 30
      const { items } = await api.calendar(daysAhead)
      setCalendar(items)
      setShowForm(false)
    } catch (err) { console.error(err) }
    finally { setSaving(false) }
  }

  async function handleDeleteEvent(ev: RbcEvent) {
    setDeleting(true)
    try {
      await api.deleteCalendar(ev.resource.id, ev.resource.changekey)
      removeCalendarItem(ev.resource.id)
      setActiveEvent(null)
    } catch (err) {
      console.error('[deleteCalendar]', err)
      // Still remove from UI — server might have deleted it even if response errored
      removeCalendarItem(ev.resource.id)
      setActiveEvent(null)
    } finally {
      setDeleting(false)
    }
  }

  // ── react-big-calendar callbacks ───────────────────────────────────────────
  const handleSelectSlot = useCallback((slot: SlotInfo) => {
    openForm(slot.start, slot.end)
  }, [])

  const handleSelectEvent = useCallback((ev: RbcEvent) => {
    setSelection({ type: 'calendar', item: ev.resource })
    setActiveEvent(ev)
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
      {/* Event action bar (visible when event is selected) */}
      {activeEvent && (
        <div className={styles.eventActionBar}>
          <span className={styles.eventActionTitle}>{activeEvent.title}</span>
          <span className={styles.eventActionTime}>
            {format(activeEvent.start, 'HH:mm')} – {format(activeEvent.end, 'HH:mm')}
          </span>
          <div className={styles.eventActionBtns}>
            <button
              className={styles.eventDeleteBtn}
              onClick={() => handleDeleteEvent(activeEvent)}
              disabled={deleting}
              title="Termin löschen"
            >
              {deleting ? '…' : '🗑 Löschen'}
            </button>
            <button className={styles.eventCloseBtnSmall} onClick={() => setActiveEvent(null)}>✕</button>
          </div>
        </div>
      )}
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

      {/* Create form modal */}
      {showForm && (
        <div className={styles.modalOverlay} onClick={(e) => e.target === e.currentTarget && setShowForm(false)}>
          <form onSubmit={handleCreate} className={styles.modal}>
            <h2 className={styles.modalTitle}>Neuer Termin</h2>
            <input className={styles.input} placeholder="Titel *" value={form.subject}
              onChange={(e) => setForm({ ...form, subject: e.target.value })} required autoFocus />
            <div className={styles.row}>
              <div>
                <label className={styles.label}>Start</label>
                <input className={styles.input} type="datetime-local" value={form.start}
                  onChange={(e) => setForm({ ...form, start: e.target.value })} required />
              </div>
              <div>
                <label className={styles.label}>Ende</label>
                <input className={styles.input} type="datetime-local" value={form.end}
                  onChange={(e) => setForm({ ...form, end: e.target.value })} required />
              </div>
            </div>
            <input className={styles.input} placeholder="Ort (optional)" value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })} />
            <input className={styles.input} placeholder="Zoom-Link (optional)" value={form.zoom_link}
              onChange={(e) => setForm({ ...form, zoom_link: e.target.value })} />
            <textarea className={styles.textarea} placeholder="Notizen (optional)" rows={2}
              value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
            <div className={styles.formActions}>
              <button type="button" className={styles.cancelBtn} onClick={() => setShowForm(false)}>Abbrechen</button>
              <button type="submit" className={styles.saveBtn} disabled={saving}>{saving ? '…' : 'Speichern'}</button>
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
            onEventClick={(ev) => setSelection({ type: 'calendar', item: ev.resource })}
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
