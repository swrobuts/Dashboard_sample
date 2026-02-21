import { api } from '../api/client'
import { useStore } from '../store/useStore'
import type { TriagedMail } from '../api/types'

let triageRunning = false

export function useDataLoader() {
  const {
    setMails, updateMail, setCalendar, setTasks,
    setLoadingMails, setLoadingCalendar, setLoadingTasks,
    user,
  } = useStore()

  async function loadMails() {
    setLoadingMails(true)
    try {
      const { emails } = await api.fetchMails(30, false)
      const initial: TriagedMail[] = emails.map((e, i) => ({
        ...e,
        id: `mail-${i}-${Date.now()}`,
        kategorie: 'Nur Info' as const,
        priorität: 3,
        zusammenfassung: '',
        empfohlene_aktion: '',
        triageStatus: 'pending' as const,
      }))
      setMails(initial)
      // Triage top 20 in batches of 5 concurrently
      if (!triageRunning) {
        triageRunning = true
        const toTriage = initial.slice(0, 20)
        const BATCH = 5
        for (let i = 0; i < toTriage.length; i += BATCH) {
          await Promise.all(
            toTriage.slice(i, i + BATCH).map(async (mail) => {
              try {
                const text = `Von: ${mail.sender}\nBetreff: ${mail.subject}\nDatum: ${mail.datetime_received ?? ''}\n\n${mail.body}`
                const result = await api.analyze(text)
                updateMail(mail.id, {
                  kategorie: result.kategorie as TriagedMail['kategorie'],
                  priorität: result.priorität,
                  zusammenfassung: result.zusammenfassung,
                  empfohlene_aktion: result.empfohlene_aktion,
                  triageStatus: 'done' as const,
                })
              } catch {
                updateMail(mail.id, { triageStatus: 'error' as const })
              }
            })
          )
        }
        triageRunning = false
      }
    } catch (e) {
      console.error('loadMails', e)
    } finally {
      setLoadingMails(false)
    }
  }

  async function loadCalendar() {
    if (!user?.ews_connected) return
    setLoadingCalendar(true)
    try {
      const { items } = await api.calendar()
      setCalendar(items)
    } catch (e) {
      console.error('loadCalendar', e)
    } finally {
      setLoadingCalendar(false)
    }
  }

  async function loadTasks() {
    if (!user?.ews_connected) return
    setLoadingTasks(true)
    try {
      const { tasks } = await api.tasks()
      setTasks(tasks)
    } catch (e) {
      console.error('loadTasks', e)
    } finally {
      setLoadingTasks(false)
    }
  }

  async function loadAll() {
    await Promise.all([loadMails(), loadCalendar(), loadTasks()])
  }

  return { loadAll, loadMails, loadCalendar, loadTasks }
}
