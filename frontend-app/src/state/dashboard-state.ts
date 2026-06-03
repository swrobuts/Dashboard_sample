import { useSearchParams } from 'react-router-dom'

/**
 * URL-as-State: gewählte Filter leben in der URL, nicht im React-State.
 * Konsequenz: Permalinks, Browser-Back und Teilen funktionieren ohne weitere Logik.
 *
 * Gegenmaßnahme zu Pre-Mortem F9 (State-Spaghetti).
 */

export type DashboardState = {
    year: number
    iso3: string | null
}

const DEFAULT_YEAR = 2025

export function useDashboardState(): [
    DashboardState,
    (patch: Partial<DashboardState>) => void,
] {
    const [params, setParams] = useSearchParams()

    const yearParam = params.get('y')
    const isoParam = params.get('c')

    const state: DashboardState = {
        year: yearParam ? Number(yearParam) : DEFAULT_YEAR,
        iso3: isoParam,
    }

    const patch = (p: Partial<DashboardState>) => {
        const next = new URLSearchParams(params)
        if (p.year !== undefined) next.set('y', String(p.year))
        if (p.iso3 !== undefined) {
            if (p.iso3) next.set('c', p.iso3)
            else next.delete('c')
        }
        setParams(next, { replace: false })
    }

    return [state, patch]
}