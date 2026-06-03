import type { CSSProperties } from 'react'
import { useDashboardState } from '../state/dashboard-state'

const stub: CSSProperties = {
    fontSize: 'var(--text-small)',
    color: 'var(--muted)',
    fontStyle: 'italic',
}

export function Ranking() {
    const [{ year }] = useDashboardState()
    return (
        <>
            <h1 style={{
                fontSize: 'var(--text-display)',
                fontWeight: 'var(--weight-medium)',
                letterSpacing: 'var(--track-display)',
                lineHeight: 'var(--leading-tight)',
                margin: 0,
            }}>
                Wer führt {year}, wer rutscht?
            </h1>
            <p style={stub}>Komponenten folgen in Schritt 7.</p>
        </>
    )
}