-- =============================================================================
-- 01_schema.sql  —  Tabellen für World-Happiness-Dashboard
-- =============================================================================
-- Entwurfsentscheidung: OBT (one-big-table) für die Fakten.
-- Rechtfertigung: 1 Quelle, 1 Grain (Land × Jahr), 1 Fakt, ~2.100 Zeilen,
-- jährliches Append-Only. Star-Schema wäre Overkill (siehe pre-mortem).
--
-- Was bleibt: zwei schlanke Lookup-Tabellen für *Land-Identität*. Die sind
-- die zentrale Gegenmaßnahme gegen F3 (Rename), F4 (Nicht-ISO-Namen) und
-- F5 (Unicode-Apostroph). Damit hängt die gesamte Pipeline an einem
-- stabilen Anker (ISO-3166-1 alpha-3), nicht an Anzeigenamen.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1) Kanonische Länder (ISO-3166-1 alpha-3 als PK)
--    X??-Codes sind ISO-3166-1 user-assigned (Kosovo, Nord-Zypern, Somaliland).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS country (
    iso3            CHAR(3)     PRIMARY KEY
                                CHECK (iso3 ~ '^[A-Z]{3}$'),
    canonical_name  TEXT        NOT NULL,
    region          TEXT,            -- optional anzureichern (z.B. via World Bank)
    is_de_facto     BOOLEAN     NOT NULL DEFAULT FALSE,   -- X??-Codes = TRUE
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE country IS
    'Kanonische Länderliste. ISO-3166-1 alpha-3 als stabiler Anker.';

-- -----------------------------------------------------------------------------
-- 2) Alias-Tabelle: jeder im WHR vorkommende Anzeigename → ISO3.
--    Wenn WHR im nächsten Release "South Korea" statt "Republic of Korea"
--    schreibt, ergänzen wir hier einen Eintrag — sonst nichts.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS country_alias (
    alias  TEXT     PRIMARY KEY,    -- exakter String aus der Quelle
    iso3   CHAR(3)  NOT NULL REFERENCES country(iso3) ON UPDATE CASCADE
);
COMMENT ON TABLE country_alias IS
    'Mapping Quell-Anzeigename → ISO3. Wird per scripts/generate_country_seed.py erzeugt.';

-- -----------------------------------------------------------------------------
-- 3) Fakt: World-Happiness-Report-Werte pro Land × Jahr.
--    Grain explizit über UNIQUE(iso3, year) — verhindert versehentliche
--    Doppelimporte (F8/F12: Refresh-Sicherheit).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS happiness (
    id                       BIGSERIAL PRIMARY KEY,
    iso3                     CHAR(3)   NOT NULL REFERENCES country(iso3),
    year                     SMALLINT  NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    rank                     SMALLINT  NOT NULL CHECK (rank > 0),
    life_evaluation          NUMERIC(6,4) NOT NULL CHECK (life_evaluation BETWEEN 0 AND 10),
    lower_whisker            NUMERIC(6,4),
    upper_whisker            NUMERIC(6,4),
    factor_log_gdp           NUMERIC(6,4),
    factor_social_support    NUMERIC(6,4),
    factor_healthy_life      NUMERIC(6,4),
    factor_freedom           NUMERIC(6,4),
    factor_generosity        NUMERIC(6,4),
    factor_corruption        NUMERIC(6,4),
    dystopia_residual        NUMERIC(6,4),
    source_url               TEXT      NOT NULL,
    ingested_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (iso3, year)
);

CREATE INDEX IF NOT EXISTS idx_happiness_year ON happiness (year);
CREATE INDEX IF NOT EXISTS idx_happiness_iso3 ON happiness (iso3);

-- -----------------------------------------------------------------------------
-- 4) Roh-Staging (nur Zwischenstation für den Import).
--    Bewusst untypisiert, damit Schema-Drift beim Laden erkannt wird
--    statt still zu kippen.  (F1)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS happiness_raw (
    year                            TEXT,
    rank                            TEXT,
    country_name                    TEXT,
    life_evaluation_3y              TEXT,
    lower_whisker                   TEXT,
    upper_whisker                   TEXT,
    explained_log_gdp               TEXT,
    explained_social_support        TEXT,
    explained_healthy_life          TEXT,
    explained_freedom               TEXT,
    explained_generosity            TEXT,
    explained_corruption            TEXT,
    dystopia_residual               TEXT,
    source_url                      TEXT,
    loaded_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE happiness_raw IS
    'Untypisierter Roh-Layer. Wird vor jedem Refresh per TRUNCATE geleert.';

COMMIT;
