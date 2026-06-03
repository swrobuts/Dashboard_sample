import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDataQuality } from '../api/happiness'

const stateMsg: CSSProperties = {
    fontSize: 'var(--text-small)',
    color: 'var(--muted)',
    margin: 'calc(var(--grid) * 2) 0',
}

const errorBox: CSSProperties = {
    fontSize: 'var(--text-small)',
    color: 'var(--neg)',
    padding: 'calc(var(--grid) * 2)',
    borderLeft: '2px solid var(--neg)',
    margin: 'calc(var(--grid) * 2) 0',
    fontFamily: 'ui-monospace, monospace',
}

const headCell: CSSProperties = {
    padding: '6px 12px',
    borderBottom: '1px solid var(--fg)',
    fontSize: 'var(--text-micro)',
    color: 'var(--muted)',
    textTransform: 'uppercase',
    letterSpacing: 'var(--track-label)',
    fontWeight: 'var(--weight-regular)',
    textAlign: 'left',
}
const numHeadCell: CSSProperties = { ...headCell, textAlign: 'right' }

const cell: CSSProperties = {
    padding: '6px 12px',
    borderBottom: '1px solid var(--rule)',
    fontSize: 'var(--text-small)',
    color: 'var(--fg)',
    fontVariantNumeric: 'tabular-nums',
}
const numCell: CSSProperties = { ...cell, textAlign: 'right' }

export function ConnectivityCheck() {
    const { data, isPending, isError, error } = useQuery({
        queryKey: ['data-quality'],
        queryFn: getDataQuality,
    })

    if (isPending) {
        return <p style={stateMsg}>Lädt Datenqualitäts-Cockpit aus Supabase …</p>
    }

    if (isError) {
        return (
            <div style={errorBox}>
                Fehler beim Laden: {error instanceof Error ? error.message : String(error)}
            </div>
        )
    }

    if (!data || data.length === 0) {
        return <p style={stateMsg}>Keine Daten zurückgegeben.</p>
    }

    return (
        <div>
            <p style={{
                fontSize: 'var(--text-small)',
                color: 'var(--muted)',
                margin: '0 0 calc(var(--grid) * 2)',
                maxWidth: '60ch',
            }}>
                {data.length} Jahre live aus{' '}
                <code style={{ fontFamily: 'ui-monospace, monospace' }}>v_data_quality</code>.
                Die Pre-Mortem-F2-Asymmetrie (Faktoren erst ab 2019) ist in der %-Spalte
                direkt erkennbar.
            </p>
            <table style={{
                width: '100%',
                maxWidth: 720,
                borderCollapse: 'collapse',
                fontVariantNumeric: 'tabular-nums',
            }}>
                <thead>
                <tr>
                    <th style={headCell}>Jahr</th>
                    <th style={numHeadCell}>Länder</th>
                    <th style={numHeadCell}>Mit Faktoren</th>
                    <th style={numHeadCell}>%</th>
                    <th style={numHeadCell}>Min</th>
                    <th style={numHeadCell}>Max</th>
                </tr>
                </thead>
                <tbody>
                {data.map(row => (
                    <tr key={row.year}>
                        <td style={cell}>{row.year}</td>
                        <td style={numCell}>{row.n_countries}</td>
                        <td style={numCell}>{row.n_with_factors}</td>
                        <td style={{
                            ...numCell,
                            color: row.pct_with_factors === 0 ? 'var(--muted)' : 'var(--fg)',
                        }}>
                            {row.pct_with_factors.toFixed(1)}
                        </td>
                        <td style={numCell}>{row.min_score.toFixed(2)}</td>
                        <td style={numCell}>{row.max_score.toFixed(2)}</td>
                    </tr>
                ))}
                </tbody>
            </table>
        </div>
    )
}