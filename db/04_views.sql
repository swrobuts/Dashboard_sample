-- =============================================================================
-- 04_views.sql  —  API-Vertrag fürs Frontend
-- =============================================================================
-- Regel: Das Frontend codet AUSSCHLIESSLICH gegen Views in diesem File.
-- Direkt-Zugriff auf `happiness` ist verboten (RLS in 05_rls.sql erzwingt).
--
-- v_happiness ist die *Single Source of Truth*.
-- Alle abgeleiteten Views (Ranking, YoY, …) beziehen sich nur auf v_happiness.
--
-- Adressiert:
--   F2  NULL-Asymmetrie  → expliziter Flag has_factor_decomposition
--   F6  Lücke 2013       → wird *nicht* synthetisiert, Frontend muss umgehen
--   F7  Zeitreihen-Gaps  → in v_country_year_grid sichtbar, kein LOCF
--   F10 SSOT             → ein einziger Ort für "Ranking", "YoY", "Faktor"
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1) SSOT: kanonischer Lesblick mit Anreicherung
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_happiness AS
SELECT
    h.iso3,
    c.canonical_name                              AS country,
    c.is_de_facto,
    h.year,
    h.rank,
    h.life_evaluation,
    h.lower_whisker,
    h.upper_whisker,
    h.factor_log_gdp,
    h.factor_social_support,
    h.factor_healthy_life,
    h.factor_freedom,
    h.factor_generosity,
    h.factor_corruption,
    h.dystopia_residual,
    -- F2: explizit kenntlich machen, ob Faktor-Zerlegung verfügbar ist.
    -- Im Datensatz: erst ab 2019 befüllt. Frontend zeigt entsprechende
    -- Charts dann nur ab 2019 und blendet sonst eine Erklärungs-Pille ein.
    (h.factor_log_gdp IS NOT NULL)                AS has_factor_decomposition,
    h.source_url
FROM happiness h
JOIN country  c USING (iso3);

COMMENT ON VIEW v_happiness IS
    'SSOT: jede Frontend-Query startet hier. Direktzugriff auf happiness ist verboten (RLS).';

-- -----------------------------------------------------------------------------
-- 2) Vollständiges Land × Jahr-Gitter — macht Lücken sichtbar (F7)
--    LEFT JOIN gegen das Kreuzprodukt; fehlende Datenpunkte bleiben NULL,
--    werden aber NIE per LOCF/Interpolation ersetzt.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_country_year_grid AS
WITH years    AS (SELECT DISTINCT year FROM happiness),
     countries AS (SELECT DISTINCT iso3 FROM happiness)
SELECT
    co.iso3,
    c.canonical_name      AS country,
    y.year,
    h.life_evaluation,
    h.rank,
    (h.life_evaluation IS NULL) AS is_gap
FROM countries co
CROSS JOIN years y
JOIN country c ON c.iso3 = co.iso3
LEFT JOIN happiness h ON h.iso3 = co.iso3 AND h.year = y.year;

-- -----------------------------------------------------------------------------
-- 3) Year-over-Year-Delta (nur über vorhandene Datenpunkte)
--    LAG ignoriert Gaps automatisch durch PARTITION BY iso3 ORDER BY year.
--    Frontend zeigt YoY = NULL als "keine Vergleichsbasis", nicht als 0.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_yoy AS
SELECT
    iso3,
    country,
    year,
    life_evaluation,
    life_evaluation
        - LAG(life_evaluation) OVER (PARTITION BY iso3 ORDER BY year)
                                            AS delta_abs,
    year - LAG(year) OVER (PARTITION BY iso3 ORDER BY year)
                                            AS years_since_last_obs
FROM v_happiness;

-- -----------------------------------------------------------------------------
-- 4) Top-N pro Jahr (kanonisches Ranking, F10 — Frontend rechnet nicht selbst)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_ranking AS
SELECT iso3, country, year, rank, life_evaluation
FROM v_happiness
ORDER BY year DESC, rank ASC;

-- -----------------------------------------------------------------------------
-- 5) Faktor-Zerlegung (nur dort, wo Daten vorhanden — F2)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_factor_decomposition AS
SELECT
    iso3, country, year, life_evaluation,
    factor_log_gdp,
    factor_social_support,
    factor_healthy_life,
    factor_freedom,
    factor_generosity,
    factor_corruption,
    dystopia_residual
FROM v_happiness
WHERE has_factor_decomposition;

-- -----------------------------------------------------------------------------
-- 6) Datenqualitäts-Cockpit (für Health-Check & Refresh-Verifikation)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_data_quality AS
SELECT
    vh.year,
    COUNT(*)                                            AS n_countries,
    COUNT(*) FILTER (WHERE vh.has_factor_decomposition) AS n_with_factors,
    ROUND(100.0 * COUNT(*) FILTER (WHERE vh.has_factor_decomposition)
                  / COUNT(*), 1)                        AS pct_with_factors,
    MIN(vh.life_evaluation)                             AS min_score,
    MAX(vh.life_evaluation)                             AS max_score,
    MAX(h.ingested_at)                                  AS last_ingested
FROM v_happiness  vh
         JOIN happiness    h  USING (iso3, year)
GROUP BY vh.year
ORDER BY vh.year;

COMMENT ON VIEW v_data_quality IS
    'Health-Check-Cockpit. Im Frontend als kleine "Über die Daten"-Seite ausgespielt.';

COMMIT;
