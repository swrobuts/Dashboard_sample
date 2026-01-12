-- ============================================================
-- World Happiness Report - PostgreSQL/Supabase Schema
-- Daten: 2015-2025 (kombiniert aus Kaggle + WHR 2025)
-- ============================================================

-- Schema erstellen (optional, falls gewünscht)
-- CREATE SCHEMA IF NOT EXISTS whr;
-- SET search_path TO whr;

-- ============================================================
-- DIMENSION: Regionen
-- ============================================================
DROP TABLE IF EXISTS dim_region CASCADE;
CREATE TABLE dim_region (
    region_id SERIAL PRIMARY KEY,
    region_name VARCHAR(100) NOT NULL UNIQUE
);

INSERT INTO dim_region (region_name) VALUES
    ('Australia and New Zealand'),
    ('Central and Eastern Europe'),
    ('Eastern Asia'),
    ('Latin America and Caribbean'),
    ('Middle East and Northern Africa'),
    ('North America'),
    ('Southeastern Asia'),
    ('Southern Asia'),
    ('Sub-Saharan Africa'),
    ('Western Europe');

-- ============================================================
-- DIMENSION: Länder
-- ============================================================
DROP TABLE IF EXISTS dim_country CASCADE;
CREATE TABLE dim_country (
    country_id SERIAL PRIMARY KEY,
    country_name VARCHAR(100) NOT NULL UNIQUE,
    region_id INTEGER REFERENCES dim_region(region_id)
);

-- ============================================================
-- FAKTEN: Happiness Scores
-- ============================================================
DROP TABLE IF EXISTS fact_happiness CASCADE;
CREATE TABLE fact_happiness (
    happiness_id SERIAL PRIMARY KEY,
    country_id INTEGER REFERENCES dim_country(country_id),
    year INTEGER NOT NULL,
    happiness_rank INTEGER,
    happiness_score DECIMAL(5,3),
    gdp DECIMAL(10,6),
    social_support DECIMAL(10,6),
    life_expectancy DECIMAL(10,6),
    freedom DECIMAL(10,6),
    generosity DECIMAL(10,6),
    corruption DECIMAL(10,6),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (country_id, year)
);

-- ============================================================
-- INDIZES für Performance
-- ============================================================
CREATE INDEX idx_fact_happiness_year ON fact_happiness(year);
CREATE INDEX idx_fact_happiness_country ON fact_happiness(country_id);
CREATE INDEX idx_fact_happiness_score ON fact_happiness(happiness_score DESC);
CREATE INDEX idx_dim_country_region ON dim_country(region_id);

-- ============================================================
-- VIEW: Denormalisierte Ansicht für einfache Abfragen
-- ============================================================
DROP VIEW IF EXISTS v_happiness_report;
CREATE VIEW v_happiness_report AS
SELECT 
    f.year,
    f.happiness_rank,
    c.country_name,
    r.region_name,
    f.happiness_score,
    f.gdp,
    f.social_support,
    f.life_expectancy,
    f.freedom,
    f.generosity,
    f.corruption
FROM fact_happiness f
JOIN dim_country c ON f.country_id = c.country_id
LEFT JOIN dim_region r ON c.region_id = r.region_id
ORDER BY f.year DESC, f.happiness_rank ASC;

-- ============================================================
-- VIEW: Länder-Ranking aktuelles Jahr
-- ============================================================
DROP VIEW IF EXISTS v_current_ranking;
CREATE VIEW v_current_ranking AS
SELECT 
    f.happiness_rank,
    c.country_name,
    r.region_name,
    f.happiness_score,
    f.gdp,
    f.social_support,
    f.freedom
FROM fact_happiness f
JOIN dim_country c ON f.country_id = c.country_id
LEFT JOIN dim_region r ON c.region_id = r.region_id
WHERE f.year = (SELECT MAX(year) FROM fact_happiness)
ORDER BY f.happiness_rank;

-- ============================================================
-- VIEW: Trends pro Land (Zeitreihe)
-- ============================================================
DROP VIEW IF EXISTS v_country_trends;
CREATE VIEW v_country_trends AS
SELECT 
    c.country_name,
    r.region_name,
    f.year,
    f.happiness_score,
    f.happiness_score - LAG(f.happiness_score) OVER (
        PARTITION BY c.country_id ORDER BY f.year
    ) AS score_change_yoy
FROM fact_happiness f
JOIN dim_country c ON f.country_id = c.country_id
LEFT JOIN dim_region r ON c.region_id = r.region_id
ORDER BY c.country_name, f.year;

-- ============================================================
-- VIEW: Regionale Durchschnitte
-- ============================================================
DROP VIEW IF EXISTS v_regional_averages;
CREATE VIEW v_regional_averages AS
SELECT 
    r.region_name,
    f.year,
    COUNT(*) AS country_count,
    ROUND(AVG(f.happiness_score)::numeric, 3) AS avg_happiness_score,
    ROUND(AVG(f.gdp)::numeric, 3) AS avg_gdp,
    ROUND(AVG(f.social_support)::numeric, 3) AS avg_social_support,
    ROUND(AVG(f.life_expectancy)::numeric, 3) AS avg_life_expectancy,
    ROUND(AVG(f.freedom)::numeric, 3) AS avg_freedom
FROM fact_happiness f
JOIN dim_country c ON f.country_id = c.country_id
JOIN dim_region r ON c.region_id = r.region_id
GROUP BY r.region_name, f.year
ORDER BY f.year DESC, avg_happiness_score DESC;

-- ============================================================
-- STORED PROCEDURE: Daten aus CSV importieren (Staging)
-- Nutzung: Nach Upload der CSV in Supabase Storage
-- ============================================================
-- Hinweis: In Supabase am einfachsten über den Table Editor 
-- oder via COPY-Befehl mit CSV importieren

-- ============================================================
-- HILFSFUNKTION: Länder und Regionen aus Staging befüllen
-- ============================================================
-- Diese Funktion kann nach dem CSV-Import ausgeführt werden:

/*
-- 1. Staging-Tabelle erstellen (temporär)
CREATE TEMP TABLE staging_whr (
    country VARCHAR(100),
    year INTEGER,
    region VARCHAR(100),
    happiness_rank INTEGER,
    happiness_score DECIMAL(5,3),
    gdp DECIMAL(10,6),
    social_support DECIMAL(10,6),
    life_expectancy DECIMAL(10,6),
    freedom DECIMAL(10,6),
    generosity DECIMAL(10,6),
    corruption DECIMAL(10,6)
);

-- 2. CSV importieren (in psql oder Supabase SQL Editor)
-- \COPY staging_whr FROM 'whr_combined_2015_2025.csv' WITH CSV HEADER;

-- 3. Länder einfügen
INSERT INTO dim_country (country_name, region_id)
SELECT DISTINCT 
    s.country,
    r.region_id
FROM staging_whr s
LEFT JOIN dim_region r ON s.region = r.region_name
ON CONFLICT (country_name) DO NOTHING;

-- 4. Fakten einfügen
INSERT INTO fact_happiness (
    country_id, year, happiness_rank, happiness_score,
    gdp, social_support, life_expectancy, freedom, generosity, corruption
)
SELECT 
    c.country_id,
    s.year,
    s.happiness_rank,
    s.happiness_score,
    s.gdp,
    s.social_support,
    s.life_expectancy,
    s.freedom,
    s.generosity,
    s.corruption
FROM staging_whr s
JOIN dim_country c ON s.country = c.country_name
ON CONFLICT (country_id, year) DO UPDATE SET
    happiness_rank = EXCLUDED.happiness_rank,
    happiness_score = EXCLUDED.happiness_score,
    gdp = EXCLUDED.gdp,
    social_support = EXCLUDED.social_support,
    life_expectancy = EXCLUDED.life_expectancy,
    freedom = EXCLUDED.freedom,
    generosity = EXCLUDED.generosity,
    corruption = EXCLUDED.corruption;

-- 5. Staging-Tabelle löschen
DROP TABLE staging_whr;
*/

-- ============================================================
-- ROW LEVEL SECURITY (optional für Supabase)
-- ============================================================
-- ALTER TABLE fact_happiness ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE dim_country ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE dim_region ENABLE ROW LEVEL SECURITY;

-- Policy für öffentlichen Lesezugriff:
-- CREATE POLICY "Public read access" ON fact_happiness FOR SELECT USING (true);
-- CREATE POLICY "Public read access" ON dim_country FOR SELECT USING (true);
-- CREATE POLICY "Public read access" ON dim_region FOR SELECT USING (true);

-- ============================================================
-- GRANT-Berechtigungen für Supabase anon/authenticated roles
-- ============================================================
-- GRANT SELECT ON v_happiness_report TO anon, authenticated;
-- GRANT SELECT ON v_current_ranking TO anon, authenticated;
-- GRANT SELECT ON v_country_trends TO anon, authenticated;
-- GRANT SELECT ON v_regional_averages TO anon, authenticated;
