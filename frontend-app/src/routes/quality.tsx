import { ConnectivityCheck } from '../components/ConnectivityCheck'

export function Quality() {
    return (
        <>
            <h1 style={{
                fontSize: 'var(--text-display)',
                fontWeight: 'var(--weight-medium)',
                letterSpacing: 'var(--track-display)',
                lineHeight: 'var(--leading-tight)',
                margin: 0,
                marginBottom: 'calc(var(--grid) * 2)',
            }}>
                Was steckt — und was nicht?
            </h1>
            <p style={{
                fontSize: 'var(--text-body)',
                color: 'var(--muted)',
                maxWidth: '60ch',
                lineHeight: 'var(--leading-loose)',
                marginBottom: 'calc(var(--grid) * 4)',
            }}>
                Die ehrliche Lückenkarte. Wann hat WHR welche Länder erhoben, ab wann
                sind Erklärfaktoren verfügbar, wo zerbricht die Datenreihe? Aus dem
                Pre-Mortem geboren, jetzt direkt sichtbar.
            </p>
            <ConnectivityCheck />
        </>
    )
}