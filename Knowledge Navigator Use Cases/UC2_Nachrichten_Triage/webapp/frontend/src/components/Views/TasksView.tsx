import { useState, useMemo } from 'react'
import { useStore } from '../../store/useStore'
import { useDataLoader } from '../../hooks/useDataLoader'
import { api } from '../../api/client'
import type { Task } from '../../api/types'
import styles from './TasksView.module.css'

type SortCol = 'subject' | 'due_date' | 'priority' | 'status'
type SortDir = 'asc' | 'desc'
type GroupBy = 'none' | 'priority' | 'status'

const PRIO_ORDER: Record<string, number> = { High: 0, Normal: 1, Low: 2 }
const STATUS_LABEL: Record<string, string> = {
  NotStarted: 'Nicht begonnen', InProgress: 'In Bearbeitung',
  WaitingOnOthers: 'Wartet', Deferred: 'Zurückgestellt', Completed: 'Erledigt',
}
const PRIO_LABEL: Record<string, string> = { High: 'Hoch', Normal: 'Normal', Low: 'Niedrig' }

export function TasksView() {
  const { tasks, setTasks, removeTask, user } = useStore()
  const { loadTasks } = useDataLoader()
  const [syncing, setSyncing] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ subject: '', due_date: '', body: '', priority: 'Normal' })
  const [saving, setSaving] = useState(false)

  const [search, setSearch] = useState('')
  const [filterPrio, setFilterPrio] = useState('all')
  const [filterStatus, setFilterStatus] = useState('all')
  const [sortCol, setSortCol] = useState<SortCol>('due_date')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [groupBy, setGroupBy] = useState<GroupBy>('none')
  const [completing, setCompleting] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)

  async function handleSync() {
    setSyncing(true)
    try { await loadTasks() } finally { setSyncing(false) }
  }

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

  async function handleComplete(task: Task) {
    setCompleting(task.id)
    try {
      await api.completeTask(task.id, task.changekey)
      removeTask(task.id)
    } catch (err) { console.error(err) }
    finally { setCompleting(null) }
  }

  async function handleDelete(task: Task) {
    setDeleting(task.id)
    try {
      await api.deleteTask(task.id, task.changekey)
      removeTask(task.id)
    } catch (err) { console.error(err) }
    finally { setDeleting(null) }
  }

  function toggleSort(col: SortCol) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('asc') }
  }

  const filtered = useMemo(() => {
    return tasks.filter(t => {
      if (search && !t.subject.toLowerCase().includes(search.toLowerCase())) return false
      if (filterPrio !== 'all' && t.priority !== filterPrio) return false
      if (filterStatus !== 'all' && t.status !== filterStatus) return false
      return true
    })
  }, [tasks, search, filterPrio, filterStatus])

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let cmp = 0
      if (sortCol === 'subject') cmp = a.subject.localeCompare(b.subject)
      else if (sortCol === 'due_date') cmp = (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999')
      else if (sortCol === 'priority') cmp = (PRIO_ORDER[a.priority] ?? 1) - (PRIO_ORDER[b.priority] ?? 1)
      else if (sortCol === 'status') cmp = (a.status ?? '').localeCompare(b.status ?? '')
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [filtered, sortCol, sortDir])

  const grouped = useMemo(() => {
    if (groupBy === 'none') return { '': sorted }
    const groups: Record<string, Task[]> = {}
    for (const t of sorted) {
      const key = groupBy === 'priority' ? (t.priority ?? 'Normal') : (t.status ?? 'NotStarted')
      if (!groups[key]) groups[key] = []
      groups[key].push(t)
    }
    if (groupBy === 'priority') {
      return Object.fromEntries(
        Object.entries(groups).sort(([a], [b]) => (PRIO_ORDER[a] ?? 1) - (PRIO_ORDER[b] ?? 1))
      )
    }
    return groups
  }, [sorted, groupBy])

  function SortIcon({ col }: { col: SortCol }) {
    if (sortCol !== col) return <span className={styles.sortNeutral}>↕</span>
    return <span className={styles.sortActive}>{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  function groupLabel(key: string) {
    if (groupBy === 'priority') return PRIO_LABEL[key] ?? key
    return STATUS_LABEL[key] ?? key
  }

  return (
    <div className={styles.view}>
      {/* ── Row 1: search + action buttons ── */}
      <div className={styles.toolbar}>
        <input
          className={styles.search}
          type="search"
          placeholder="Aufgabe suchen…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <button className={styles.syncBtn} onClick={handleSync} disabled={syncing} title="Aufgaben neu laden">
          {syncing ? '⏳' : '↻'}
        </button>
        {user?.ews_connected && (
          <button className={styles.addBtn} onClick={() => setShowForm(!showForm)}>+ Neu</button>
        )}
      </div>

      {/* ── Row 2: filter dropdowns (only with EWS) ── */}
      {user?.ews_connected && (
        <div className={styles.filterBar}>
          <select className={styles.filter} value={filterPrio} onChange={e => setFilterPrio(e.target.value)}>
            <option value="all">Alle Prioritäten</option>
            <option value="High">Hoch</option>
            <option value="Normal">Normal</option>
            <option value="Low">Niedrig</option>
          </select>
          <select className={styles.filter} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
            <option value="all">Alle Status</option>
            <option value="NotStarted">Nicht begonnen</option>
            <option value="InProgress">In Bearbeitung</option>
            <option value="WaitingOnOthers">Wartet</option>
            <option value="Deferred">Zurückgestellt</option>
          </select>
          <select className={styles.filter} value={groupBy} onChange={e => setGroupBy(e.target.value as GroupBy)}>
            <option value="none">Keine Gruppierung</option>
            <option value="priority">Nach Priorität</option>
            <option value="status">Nach Status</option>
          </select>
          <span className={styles.count}>{filtered.length} Aufgabe{filtered.length !== 1 ? 'n' : ''}</span>
        </div>
      )}

      {!user?.ews_connected && (
        <p className={styles.noEws}>
          Exchange nicht verbunden — Aufgaben nicht verfügbar.
          {user?.ews_error && (
            <><br /><small>{user.ews_error}</small><br /><small>Bitte beim Login die korrekte Exchange-E-Mail eingeben.</small></>
          )}
        </p>
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
            onChange={(e) => setForm({ ...form, body: e.target.value })} rows={2} />
          <div className={styles.formActions}>
            <button type="button" className={styles.cancelBtn} onClick={() => setShowForm(false)}>Abbrechen</button>
            <button type="submit" className={styles.saveBtn} disabled={saving}>{saving ? '…' : 'Speichern'}</button>
          </div>
        </form>
      )}

      {/* ── Table (fills remaining height) ── */}
      {user?.ews_connected && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={`${styles.th} ${styles.thSubject}`} onClick={() => toggleSort('subject')}>
                  Aufgabe <SortIcon col="subject" />
                </th>
                <th className={styles.th} onClick={() => toggleSort('due_date')}>
                  Fällig <SortIcon col="due_date" />
                </th>
                <th className={styles.th} onClick={() => toggleSort('priority')}>
                  Prio <SortIcon col="priority" />
                </th>
                <th className={styles.th} onClick={() => toggleSort('status')}>
                  Status <SortIcon col="status" />
                </th>
                <th className={styles.th}>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(grouped).map(([groupKey, groupTasks]) => (
                <>
                  {groupBy !== 'none' && (
                    <tr key={`grp-${groupKey}`} className={styles.groupRow}>
                      <td colSpan={5} className={styles.groupLabel}>{groupLabel(groupKey)}</td>
                    </tr>
                  )}
                  {groupTasks.map(task => (
                    <tr key={task.id} className={styles.tr}>
                      <td className={styles.tdSubject}>{task.subject}</td>
                      <td className={styles.td}>
                        {task.due_date
                          ? <span className={isOverdue(task.due_date) ? styles.overdue : ''}>{task.due_date.slice(0, 10)}</span>
                          : <span className={styles.noDate}>—</span>}
                      </td>
                      <td className={styles.td}>
                        <span className={`${styles.prioBadge} ${styles[task.priority?.toLowerCase() ?? 'normal']}`}>
                          {PRIO_LABEL[task.priority] ?? task.priority}
                        </span>
                      </td>
                      <td className={styles.td}>
                        <span className={styles.statusText}>{STATUS_LABEL[task.status] ?? task.status}</span>
                      </td>
                      <td className={styles.tdActions}>
                        <button
                          className={styles.doneBtn}
                          onClick={() => handleComplete(task)}
                          disabled={completing === task.id}
                          title="Als erledigt markieren"
                        >
                          {completing === task.id ? '…' : '✓'}
                        </button>
                        <button
                          className={styles.deleteBtn}
                          onClick={() => handleDelete(task)}
                          disabled={deleting === task.id}
                          title="Löschen"
                        >
                          {deleting === task.id ? '…' : '✕'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.empty}>
                    {tasks.length === 0 ? 'Keine offenen Aufgaben.' : 'Keine Aufgaben entsprechen dem Filter.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function isOverdue(dateStr: string): boolean {
  const today = new Date().toISOString().slice(0, 10)
  return dateStr < today
}
