import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getRanking, getAllTimeseries } from '../api/happiness'
import type { RankingRow } from '../api/happiness'
import { Sparkline } from './Sparkline'
import { Whisker } from './Whisker'

const YEAR_RANGE = [
    2011, 2012, 2014, 2015, 2016, 2017, 2018,
    2019, 2020, 2021, 2022, 2023, 2024, 2025,
]

type SortColumn = 'rank' | 'country' | 'life_evaluation'
type SortDirection = 'asc' | 'desc'
type ScaleMode = 'shared' | 'individual'

type RankingTableProps = {
    year: number
    limit?: number
}

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

const sortableHead: CSSProperties = {
    ...headCell,
    cursor: 'pointer',
    userSelect: 'none',
}
const sortableNumHead: CSSProperties = {
    ...numHeadCell,
    cursor: 'pointer',
    userSelect: 'none',
}

const cell: CSSProperties = {
    padding: '8px 12px',
    borderBottom: '1px solid var(--rule)',
    fontSize: 'var(--text-small)',
    color: 'var(--fg)',
    fontVariantNumeric: 'tabular-nums',
}
const numCell: CSSProperties = { ...cell, textAlign: 'right' }

const toolbarStyle: CSSProperties = {
    display: 'flex',
    gap: 'calc(var(--grid) * 2)',
    alignItems: 'baseline',
    marginBottom: 'calc(var(--grid) * 3)',
}

const toolbarLabel: CSSProperties = {
    fontSize: 'var(--text-micro)',
    color: 'var(--muted)',
    textTransform: 'uppercase',
    letterSpacing: 'var(--track-label)',
    marginRight: 'var(--grid)',
}

const toggleButton = (active: boolean): CSSProperties => ({
    fontSize: 'var(--text-small)',
    color: active ? 'var(--fg)' : 'var(--muted)',
    fontWeight: active ? 'var(--weight-medium)' : 'var(--weight-regular)',
    borderBottom: active ? '2px solid var(--fg)' : '2px solid transparent',
    padding: '2px 0',
})

function sortArrow(active: boolean, direction: SortDirection): string {
    if (!active) return ''
    return direction === 'asc' ? '  ▲' : '  ▼'
}

export function RankingTable({ year, limit = 25 }: RankingTableProps) {
    // Lokaler UI-State (nicht in URL — explorativ, nicht permalink-würdig)
    const [sortBy, setSortBy] = useState<SortColumn>('rank')
    const [sortDir, setSortDir] = useState<SortDirection>('asc')
    const [scaleMode, setScaleMode] = useState<ScaleMode>('shared')

    const rankingQ = useQuery({
        queryKey: ['ranking', year, limit],
        queryFn: () => getRanking(year, limit),
    })

    const tsQ = useQuery({
        queryKey: ['all-timeseries'],
        queryFn: getAllTimeseries,
    })

    if (rankingQ.isPending || tsQ.isPending) {
        return <p style={stateMsg}>Lädt Ranking und Zeitverläufe …</p>
    }

    if (rankingQ.isError || tsQ.isError) {
        const err = rankingQ.error ?? tsQ.error
        return (
            <div style={errorBox}>
                Fehler beim Laden: {err instanceof Error ? err.message : String(err)}
            </div>
        )
    }

    const ranking = rankingQ.data ?? []
    const timeseries = tsQ.data ?? []

    if (ranking.length === 0) {
        return <p style={stateMsg}>Keine Ranking-Daten für {year}.</p>
    }

    // Sortierung anwenden
    const sorted: RankingRow[] = [...ranking].sort((a, b) => {
        let cmp: number
        if (sortBy === 'country') {
            cmp = a.country.localeCompare(b.country)
        } else {
            cmp = a[sortBy] - b[sortBy]
        }
        return sortDir === 'asc' ? cmp : -cmp
    })

    // Zeitreihen nach iso3 gruppieren, mit Nulls für fehlende Jahre
    const tsByIso = new Map<string, (number | null)[]>()
    for (const point of timeseries) {
        if (!tsByIso.has(point.iso3)) {
            tsByIso.set(point.iso3, new Array(YEAR_RANGE.length).fill(null))
        }
        const idx = YEAR_RANGE.indexOf(point.year)
        if (idx >= 0) {
            tsByIso.get(point.iso3)![idx] = point.life_evaluation
        }
    }

    // Whisker-Achse: gemeinsam über die angezeigten Top-N
    const lowers = ranking.map(r => r.lower_whisker).filter((v): v is number => v != null)
    const uppers = ranking.map(r => r.upper_whisker).filter((v): v is number => v != null)
    const values = ranking.map(r => r.life_evaluation)
    const axisMin = lowers.length ? Math.min(...lowers) : Math.min(...values)
    const axisMax = uppers.length ? Math.max(...uppers) : Math.max(...values)

    // Sparkline-Skala — nur im "Vergleichbar"-Modus berechnen
    let sparkScaleMin: number | undefined
    let sparkScaleMax: number | undefined
    if (scaleMode === 'shared') {
        const allValues: number[] = []
        for (const row of sorted) {
            const series = tsByIso.get(row.iso3) ?? []
            for (const v of series) if (v != null) allValues.push(v)
        }
        if (allValues.length > 0) {
            const dataMin = Math.min(...allValues)
            const dataMax = Math.max(...allValues)
            const padding = (dataMax - dataMin) * 0.05
            sparkScaleMin = dataMin - padding
            sparkScaleMax = dataMax + padding
        }
    }

    const currentYearIndex = YEAR_RANGE.indexOf(year)

    const handleSort = (col: SortColumn) => {
        if (sortBy === col) {
            setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
        } else {
            setSortBy(col)
            // Sinnvolle Default-Richtungen pro Spalte
            setSortDir(col === 'life_evaluation' ? 'desc' : 'asc')
        }
    }

    return (
        <div>
            {/* Skala-Toggle */}
            <div style={toolbarStyle}>
                <span style={toolbarLabel}>Sparkline-Skala</span>
                <button
                    onClick={() => setScaleMode('shared')}
                    style={toggleButton(scaleMode === 'shared')}
                >
                    Vergleichbar
                </button>
                <button
                    onClick={() => setScaleMode('individual')}
                    style={toggleButton(scaleMode === 'individual')}
                >
                    Trend
                </button>
            </div>

            <table style={{
                width: '100%',
                maxWidth: 880,
                borderCollapse: 'collapse',
            }}>
                <thead>
                <tr>
                    <th style={sortableNumHead} onClick={() => handleSort('rank')}>
                        Rang{sortArrow(sortBy === 'rank', sortDir)}
                    </th>
                    <th style={sortableHead} onClick={() => handleSort('country')}>
                        Land{sortArrow(sortBy === 'country', sortDir)}
                    </th>
                    <th style={sortableNumHead} onClick={() => handleSort('life_evaluation')}>
                        Score{sortArrow(sortBy === 'life_evaluation', sortDir)}
                    </th>
                    <th style={headCell}>Verlauf 2011 → 2025</th>
                    <th style={headCell}>Konfidenz</th>
                </tr>
                </thead>
                <tbody>
                {sorted.map(row => (
                    <tr key={row.iso3}>
                        <td style={{ ...numCell, color: 'var(--muted)' }}>{row.rank}</td>
                        <td style={cell}>{row.country}</td>
                        <td style={{ ...numCell, fontWeight: 'var(--weight-medium)' }}>
                            {row.life_evaluation.toFixed(2)}
                        </td>
                        <td style={cell}>
                            <Sparkline
                                data={tsByIso.get(row.iso3) ?? []}
                                width={140}
                                height={20}
                                highlightIndex={currentYearIndex}
                                scaleMin={sparkScaleMin}
                                scaleMax={sparkScaleMax}
                            />
                        </td>
                        <td style={cell}>
                            <Whisker
                                lower={row.lower_whisker}
                                value={row.life_evaluation}
                                upper={row.upper_whisker}
                                axisMin={axisMin}
                                axisMax={axisMax}
                                width={120}
                                height={18}
                            />
                        </td>
                    </tr>
                ))}
                </tbody>
            </table>
        </div>
    )
}