import { useState } from 'react'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import styles from './CalendarView.module.css'

export function CalendarView() {
  const { calendar, setCalendar, user, setSelection, selection } = useStore()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ subject: '', start: '', end: '', location: '' })
  const [saving, setSaving] = useState(false)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.createCalendar(form.subject, form.start, form.end, form.location)
      const { items } = await api.calendar()
      setCalendar(items)
      setShowForm(false)
      setForm({ subject: '', start: '', end: '', location: '' })
    } catch (err) { console.error(err) }
    finally { setSaving(false) }
  }

  const grouped = calendar.reduce((acc, item) => {
    const day = item.start?.slice(0, 10) ?? 'unbekannt'
    acc[day] = acc[day] ?? []
    acc[day].push(item)
    return acc
  }, {} as Record<string, typeof calendar>)

  const days = Object.keys(grouped).sort()

  return (
    <div className={styles.view}>
      <header className={styles.header}>
        <h1 className={styles.title}>Kalender</h1>
        {user?.ews_connected && (
          <button className={styles.addBtn} onClick={() => setShowForm(!showForm)}>+ Neu</button>
        )}
      </header>

      {!user?.ews_connected && (
        <p className={styles.noEws}>EWS nicht verbunden — Kalender nicht verfügbar.</p>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className={styles.form}>
          <input className={styles.input} placeholder="Titel" value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })} required />
          <div className={styles.row}>
            <input className={styles.input} type="datetime-local" value={form.start}
              onChange={(e) => setForm({ ...form, start: e.target.value })} required />
            <input className={styles.input} type="datetime-local" value={form.end}
              onChange={(e) => setForm({ ...form, end: e.target.value })} required />
          </div>
          <input className={styles.input} placeholder="Ort (optional)" value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })} />
          <div className={styles.formActions}>
            <button type="button" className={styles.cancelBtn} onClick={() => setShowForm(false)}>Abbrechen</button>
            <button type="submit" className={styles.saveBtn} disabled={saving}>{saving ? '…' : 'Speichern'}</button>
          </div>
        </form>
      )}

      <div className={styles.agenda}>
        {days.length === 0 && user?.ews_connected && (
          <p className={styles.empty}>Keine Termine in den nächsten 14 Tagen.</p>
        )}
        {days.map((day) => (
          <div key={day} className={styles.dayGroup}>
            <h3 className={styles.dayLabel}>
              {new Date(day + 'T00:00:00').toLocaleDateString('de-DE', {
                weekday: 'long', day: 'numeric', month: 'long'
              })}
            </h3>
            {grouped[day].map((item) => {
              const isSelected = selection?.type === 'calendar' && selection.item.id === item.id
              return (
                <div
                  key={item.id}
                  className={`${styles.event} ${isSelected ? styles.selected : ''}`}
                  onClick={() => setSelection({ type: 'calendar', item })}
                >
                  <div className={styles.timeBar} />
                  <div className={styles.eventContent}>
                    <p className={styles.eventTime}>
                      {item.start
                        ? new Date(item.start).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
                        : ''}
                      {item.end
                        ? ' – ' + new Date(item.end).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
                        : ''}
                    </p>
                    <p className={styles.eventTitle}>{item.subject}</p>
                    {item.location && <p className={styles.eventLoc}>📍 {item.location}</p>}
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
