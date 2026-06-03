import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!url || !anonKey) {
    throw new Error(
        'Supabase-Env-Variablen fehlen. ' +
        'Bitte .env in frontend-app/ prüfen: VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY.'
    )
}

/**
 * Einziger Supabase-Client der App.
 * Jede Query gegen die API geht über diesen Export.
 * Direkter Tabellen-Zugriff ist über RLS blockiert — auch hier nur Views nutzen.
 */
export const supabase = createClient(url, anonKey)