import { useState } from 'react'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import styles from './TasksView.module.css'

const PRIORITY_COLORS: Record<string, string> = {
  High: 'high', Normal: 'normal', Low: 'low',
}

export function TasksView() {
  const { tasks, setTasks, removeTask, user, setSelection, selection } = useStore()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ subject: '', due_date: '', body: '', priority: 'Normal' })
  const [saving, setSaving] = useState(false)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.createTask(form.subject, form.due_date || undefined, form.body, form.priority)
      const { tasks: fresh } = await api.tasks()
      setTasks(fresh)
      setShowForm(false)
      setForm({ subject: '', due_date: '', body: '', priority: 'Normal' })
    } catch (err) { console.error(err) }
    finally { setSaving(false) }
  }

  async function handleComplete(id: string, changekey: string) {
    try {
      await api.completeTask(id, changekey)
      removeTask(id)
    } catch (err) { console.error(err) }
  }

  const sorted = [...tasks].sort((a, b) => {
    const prio: Record<string, number> = { High: 0, Normal: 1, Low: 2 }
    return (prio[a.priority] ?? 1) - (prio[b.priority] ?? 1)
  })

  return (
    <div className={styles.view}>
      <header className={styles.header}>
        <h1 className={styles.title}>Aufgaben</h1>
        {user?.ews_connected && (
          <button className={styles.addBtn} onClick={() => setShowForm(!showForm)}>+ Neu</button>
        )}
      </header>

      {!user?.ews_connected && (
        <p className={styles.noEws}>EWS nicht verbunden — Aufgaben nicht verfügbar.</p>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className={styles.form}>
          <input className={styles.input} placeholder="Titel" value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })} required />
          <div className={styles.row}>
            <input className={styles.input} type="date" value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            <select className={styles.input} value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              <option value="High">Hoch</option>
              <option value="Normal">Normal</option>
              <option value="Low">Niedrig</option>
            </select>
          </div>
          <textarea className={styles.textarea} placeholder="Notizen…" value={form.body}
            onChange={(e) => setForm({ ...form, body: e.target.value })} rows={3} />
          <div className={styles.formActions}>
            <button type="button" className={styles.cancelBtn} onClick={() => setShowForm(false)}>Abbrechen</button>
            <button type="submit" className={styles.saveBtn} disabled={saving}>{saving ? '…' : 'Speichern'}</button>
          </div>
        </form>
      )}

      <div className={styles.list}>
        {sorted.length === 0 && user?.ews_connected && (
          <p className={styles.empty}>Keine offenen Aufgaben.</p>
        )}
        {sorted.map((task) => {
          const isSelected = selection?.type === 'task' && selection.item.id === task.id
          return (
            <div
              key={task.id}
              className={`${styles.task} ${isSelected ? styles.selected : ''}`}
              onClick={() => setSelection({ type: 'task', item: task })}
            >
              <button
                className={styles.checkbox}
                onClick={(e) => { e.stopPropagation(); handleComplete(task.id, task.changekey) }}
                title="Als erledigt markieren"
              >○</button>
              <div className={styles.taskContent}>
                <p className={styles.taskTitle}>{task.subject}</p>
                {task.due_date && (
                  <p className={styles.taskDue}>Fällig: {task.due_date.slice(0, 10)}</p>
                )}
              </div>
              <span className={`${styles.prioBadge} ${styles[PRIORITY_COLORS[task.priority] ?? 'normal']}`}>
                {task.priority}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
