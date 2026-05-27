-- =============================================================================
-- 05_rls.sql  —  Read-only Row-Level Security für die anon-Rolle
-- =============================================================================
-- Adressiert F8: Frontend nutzt den anon-Key (er ist *öffentlich*, soll es
-- auch sein). Damit darf anon ausschließlich die View-Schicht lesen — keine
-- Tabellen, keine Schreibzugriffe, kein Massen-DELETE.
--
-- Annahme: Supabase / PostgREST-Setup mit Rolle `anon`.
-- =============================================================================

BEGIN;

-- 1) Default: alle Rechte auf die Faktentabellen entziehen
REVOKE ALL ON happiness, happiness_raw, country, country_alias FROM anon;

-- 2) RLS auf die Faktentabelle aktivieren (kein direkter Zugriff)
ALTER TABLE happiness ENABLE ROW LEVEL SECURITY;
ALTER TABLE happiness FORCE ROW LEVEL SECURITY;
-- Keine Policy → anon sieht via Tabelle effektiv nichts.

-- 3) Lese-Zugriff explizit nur auf die Views erlauben
GRANT SELECT ON
    v_happiness,
    v_country_year_grid,
    v_yoy,
    v_ranking,
    v_factor_decomposition,
    v_data_quality
TO anon;

-- 4) Schema-Usage (Supabase-Standard: public)
GRANT USAGE ON SCHEMA public TO anon;

COMMIT;

-- -----------------------------------------------------------------------------
-- Verifikation (sollte 0 Zeilen liefern):
--   SET ROLE anon;
--   SELECT * FROM happiness LIMIT 1;     -- ERROR: permission denied
--   SELECT * FROM v_happiness LIMIT 1;   -- OK
--   RESET ROLE;
-- -----------------------------------------------------------------------------
