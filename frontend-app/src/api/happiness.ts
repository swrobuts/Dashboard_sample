import { supabase } from './supabase'

/**
 * Eine Zeile aus v_data_quality — Health-Check-Cockpit pro Jahr.
 * Felder genau so wie in der View definiert.
 */
export type DataQualityRow = {
    year: number
    n_countries: number
    n_with_factors: number
    pct_with_factors: number
    min_score: number
    max_score: number
    last_ingested: string  // ISO-Timestamp als String
}

/**
 * Liefert alle 14 Jahre aus v_data_quality, chronologisch.
 *
 * Hinweis zur Konvertierung: PostgREST liefert NUMERIC-Werte aus
 * Präzisionsgründen oft als String, BIGINT-Counts manchmal auch.
 * Wir konvertieren explizit zu number, damit Komponenten arithmetisch
 * sauber arbeiten können und Recharts keine Achsen-Bug-Show liefert.
 */
export async function getDataQuality(): Promise<DataQualityRow[]> {
    const { data, error } = await supabase
        .from('v_data_quality')
        .select('*')
        .order('year')

    if (error) throw error

    return (data ?? []).map((row: Record<string, unknown>) => ({
        year:              Number(row.year),
        n_countries:       Number(row.n_countries),
        n_with_factors:    Number(row.n_with_factors),
        pct_with_factors:  Number(row.pct_with_factors),
        min_score:         Number(row.min_score),
        max_score:         Number(row.max_score),
        last_ingested:     String(row.last_ingested),
    }))
}