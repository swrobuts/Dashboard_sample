import { useState } from 'react'
import { api } from '../../api/client'
import type { User } from '../../api/types'
import styles from './Login.module.css'

const INSTITUTIONS = ['THWS', 'DHBW']

interface Props { onLogin: (user: User) => void }

export function Login({ onLogin }: Props) {
  const [institution, setInstitution] = useState('THWS')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [lockoutSecs, setLockoutSecs] = useState(0)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.login(username, password, institution)
      onLogin({
        username: data.username,
        institution: data.institution,
        inbox_count: data.inbox_count,
        ews_connected: data.ews_connected,
      })
    } catch (err: unknown) {
      const e = err as { status?: number; data?: { detail?: { retry_after?: number } } }
      if (e.status === 429) {
        setLockoutSecs(e.data?.detail?.retry_after ?? 300)
      } else {
        setError('Ungültige Anmeldedaten')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <img src="/phil.png" className={styles.avatar} alt="PHIL" />
        <h1 className={styles.title}>PHIL</h1>
        <p className={styles.subtitle}>Persönlicher Hochschul-Assistent</p>

        <form onSubmit={handleSubmit} className={styles.form} noValidate>
          <select
            className={styles.select}
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
          >
            {INSTITUTIONS.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
          <input
            className={styles.input}
            type="text"
            placeholder="Benutzername"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
          <input
            className={styles.input}
            type="password"
            placeholder="Passwort"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
          {error && <p className={styles.error}>{error}</p>}
          {lockoutSecs > 0 && (
            <p className={styles.lockout}>
              Zu viele Fehlversuche. Bitte {Math.ceil(lockoutSecs / 60)} Min. warten.
            </p>
          )}
          <button className={styles.btn} type="submit" disabled={loading || lockoutSecs > 0}>
            {loading ? 'Verbinde…' : 'Anmelden'}
          </button>
        </form>
        <p className={styles.notice}>Credentials werden nicht gespeichert.</p>
      </div>
    </div>
  )
}
