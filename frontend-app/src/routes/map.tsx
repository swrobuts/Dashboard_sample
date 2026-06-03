import type { CSSProperties } from 'react'

const stub: CSSProperties = {
    fontSize: 'var(--text-small)',
    color: 'var(--muted)',
    fontStyle: 'italic',
}

export function Map() {
    return (
        <>
            <h1 style={{
                fontSize: 'var(--text-display)',
                fontWeight: 'var(--weight-medium)',
                letterSpacing: 'var(--track-display)',
                lineHeight: 'var(--leading-tight)',
                margin: 0,
            }}>
                Wo liegen die zufriedenen Länder?
            </h1>
            <p style={stub}>Komponenten folgen in Schritt 8.</p>
        </>
    )
}