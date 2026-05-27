-- =============================================================================
-- 03_ingest.sql  —  Idempotenter Import aus happiness_raw → happiness
-- =============================================================================
-- Annahme: scripts/load_raw.sh oder \copy hat happiness_raw frisch befüllt
-- (siehe README, Schritt 3).
--
-- Adressiert:
--   F1  Schema-Drift     → expliziter Spaltenvertrag, Cast scheitert laut
--   F3  Land-Aliase      → JOIN über country_alias.alias
--   F8  Doppelimport     → ON CONFLICT (iso3, year) DO UPDATE
--   F12 Refresh-Pfad     → ein einziger SQL-Block, vollständig idempotent
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1) Vorab-Assertions. Lieber jetzt laut scheitern als später still falsch.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    n_raw         INT;
    n_unknown     INT;
    unknown_list  TEXT;
BEGIN
    SELECT COUNT(*) INTO n_raw FROM happiness_raw;
    IF n_raw = 0 THEN
        RAISE EXCEPTION 'happiness_raw ist leer — Roh-Import vergessen?';
    END IF;

    -- F3/F4: Jeder Quell-Anzeigename muss als Alias bekannt sein.
    -- Sonst Stopp + Liste, was fehlt.
    SELECT COUNT(DISTINCT r.country_name),
           string_agg(DISTINCT r.country_name, ', ')
      INTO n_unknown, unknown_list
      FROM happiness_raw r
      LEFT JOIN country_alias a ON a.alias = r.country_name
     WHERE a.iso3 IS NULL;

    IF n_unknown > 0 THEN
        RAISE EXCEPTION
            'Unbekannte Ländernamen (%): %. '
            'Bitte scripts/generate_country_seed.py erweitern und 02_seed_countries.sql neu laden.',
            n_unknown, unknown_list;
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- 2) Upsert in die typisierte Faktentabelle.
--    NULLIF('', ...) fängt leere Strings ab, die aus CSV-Imports kommen.
-- -----------------------------------------------------------------------------
INSERT INTO happiness (
    iso3, year, rank, life_evaluation,
    lower_whisker, upper_whisker,
    factor_log_gdp, factor_social_support, factor_healthy_life,
    factor_freedom, factor_generosity, factor_corruption,
    dystopia_residual, source_url
)
SELECT
    a.iso3,
    NULLIF(r.year,                       '')::SMALLINT,
    NULLIF(r.rank,                       '')::SMALLINT,
    NULLIF(r.life_evaluation_3y,         '')::NUMERIC,
    NULLIF(r.lower_whisker,              '')::NUMERIC,
    NULLIF(r.upper_whisker,              '')::NUMERIC,
    NULLIF(r.explained_log_gdp,          '')::NUMERIC,
    NULLIF(r.explained_social_support,   '')::NUMERIC,
    NULLIF(r.explained_healthy_life,     '')::NUMERIC,
    NULLIF(r.explained_freedom,          '')::NUMERIC,
    NULLIF(r.explained_generosity,       '')::NUMERIC,
    NULLIF(r.explained_corruption,       '')::NUMERIC,
    NULLIF(r.dystopia_residual,          '')::NUMERIC,
    r.source_url
FROM happiness_raw r
JOIN country_alias a ON a.alias = r.country_name
ON CONFLICT (iso3, year) DO UPDATE SET
    rank                  = EXCLUDED.rank,
    life_evaluation       = EXCLUDED.life_evaluation,
    lower_whisker         = EXCLUDED.lower_whisker,
    upper_whisker         = EXCLUDED.upper_whisker,
    factor_log_gdp        = EXCLUDED.factor_log_gdp,
    factor_social_support = EXCLUDED.factor_social_support,
    factor_healthy_life   = EXCLUDED.factor_healthy_life,
    factor_freedom        = EXCLUDED.factor_freedom,
    factor_generosity     = EXCLUDED.factor_generosity,
    factor_corruption     = EXCLUDED.factor_corruption,
    dystopia_residual     = EXCLUDED.dystopia_residual,
    source_url            = EXCLUDED.source_url,
    ingested_at           = now();

-- -----------------------------------------------------------------------------
-- 3) Roh-Layer wieder leeren — Bronze ist Zwischenstation, kein Archiv.
-- -----------------------------------------------------------------------------
TRUNCATE TABLE happiness_raw;

COMMIT;

-- -----------------------------------------------------------------------------
-- Post-Load-Smoke-Test (manuell):
--   SELECT year, COUNT(*) AS n FROM happiness GROUP BY year ORDER BY year;
--   → Sollte 14 Jahre zeigen (2011-2025 ohne 2013).
-- -----------------------------------------------------------------------------
