import { useEffect } from 'react'
import { api } from './api/client'
import { useStore } from './store/useStore'
import { Login } from './components/Login/Login'
import { AppShell } from './components/Layout/AppShell'
import { Dashboard } from './components/Views/Dashboard'
import { MailsView } from './components/Views/MailsView'
import { CalendarView } from './components/Views/CalendarView'
import { TasksView } from './components/Views/TasksView'
import { useDataLoader } from './hooks/useDataLoader'
import type { User } from './api/types'

function ViewRouter() {
  const view = useStore((s) => s.view)
  if (view === 'dashboard') return <Dashboard />
  if (view === 'mails') return <MailsView />
  if (view === 'calendar') return <CalendarView />
  if (view === 'tasks') return <TasksView />
  return null
}

export default function App() {
  const { user, setUser } = useStore()
  const { loadAll } = useDataLoader()

  useEffect(() => {
    api.me()
      .then((u) => {
        setUser(u)
        loadAll()
      })
      .catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleLogin(u: User) {
    setUser(u)
    loadAll()
  }

  if (!user) return <Login onLogin={handleLogin} />

  return (
    <AppShell>
      <ViewRouter />
    </AppShell>
  )
}
