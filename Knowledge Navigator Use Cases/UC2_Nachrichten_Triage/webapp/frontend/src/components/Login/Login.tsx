import { useState } from 'react'
import { api } from '../../api/client'
import type { User, LLMMode } from '../../api/types'
import styles from './Login.module.css'

const INSTITUTIONS = ['THWS', 'DHBW']

const LLM_MODES: { value: LLMMode; icon: string; label: string; hint: string }[] = [
  { value: 'cloud',  icon: '☁',  label: 'Cloud',  hint: 'Claude API (Anthropic)' },
  { value: 'hybrid', icon: '⚡', label: 'Hybrid', hint: 'Triage lokal, Chat Cloud' },
  { value: 'local',  icon: '💻', label: 'Lokal',  hint: 'LM Studio (localhost)' },
]

interface Props { onLogin: (user: User) => void }

export function Login({ onLogin }: Props) {
  const [institution, setInstitution] = useState(() => localStorage.getItem('phil_institution') ?? 'THWS')
  const [username, setUsername] = useState(() => localStorage.getItem('phil_username') ?? '')
  const [password, setPassword] = useState('')
  const [exchangeEmail, setExchangeEmail] = useState(() => localStorage.getItem('phil_exchange_email') ?? '')
  const [llmMode, setLlmMode] = useState<LLMMode>(() => (localStorage.getItem('phil_llm_mode') as LLMMode) ?? 'cloud')
  const [error, setError] = useState('')
  const [lockoutSecs, setLockoutSecs] = useState(0)
  const [loading, setLoading] = useState(false)

  const needsExchangeEmail = institution === 'THWS'

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api.login(
        username, password, institution,
        needsExchangeEmail && exchangeEmail ? exchangeEmail : undefined,
        llmMode
      )
      localStorage.setItem('phil_institution', institution)
      localStorage.setItem('phil_username', username)
      localStorage.setItem('phil_llm_mode', llmMode)
      if (needsExchangeEmail && exchangeEmail) {
        localStorage.setItem('phil_exchange_email', exchangeEmail)
      }
      onLogin({
        username: data.username,
        first_name: data.first_name,
        institution: data.institution,
        inbox_count: data.inbox_count,
        ews_connected: data.ews_connected,
        ews_error: data.ews_error,
        llm_mode: data.llm_mode ?? llmMode,
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
          {needsExchangeEmail && (
            <input
              className={styles.input}
              type="email"
              placeholder="Exchange-E-Mail (z.B. robert.butscher@fhws.de)"
              value={exchangeEmail}
              onChange={(e) => setExchangeEmail(e.target.value)}
              autoComplete="email"
            />
          )}

          {/* ── LLM-Modus Toggle ─────────────────────────────────── */}
          <div className={styles.llmToggle}>
            <span className={styles.llmLabel}>KI-Verarbeitung</span>
            <div className={styles.llmChips}>
              {LLM_MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  className={`${styles.llmChip} ${llmMode === m.value ? styles.llmChipActive : ''}`}
                  onClick={() => setLlmMode(m.value)}
                  title={m.hint}
                >
                  <span className={styles.llmChipIcon}>{m.icon}</span>
                  {m.label}
                </button>
              ))}
            </div>
          </div>

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
        <p className={styles.notice}>Passwort wird nicht gespeichert.</p>
      </div>
    </div>
  )
}
