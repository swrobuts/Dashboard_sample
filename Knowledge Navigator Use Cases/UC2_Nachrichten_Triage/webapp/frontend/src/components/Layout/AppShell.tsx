import { useState } from 'react'
import { Sidebar } from './Sidebar'
import { PhilPanel } from '../Phil/PhilPanel'
import styles from './AppShell.module.css'

interface Props { children: React.ReactNode }

export function AppShell({ children }: Props) {
  const [philOpen, setPhilOpen] = useState(true)

  return (
    <div className={styles.shell} data-phil-open={philOpen ? 'true' : 'false'}>
      <Sidebar onOpenPhil={() => setPhilOpen(true)} />
      <main className={styles.content}>{children}</main>
      <PhilPanel open={philOpen} onClose={() => setPhilOpen(false)} />
      {philOpen && (
        <div className={`${styles.backdrop} ${styles.mobileOnly}`} onClick={() => setPhilOpen(false)} />
      )}
    </div>
  )
}
