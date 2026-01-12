-- ============================================================
-- World Happiness Report - MS SQL Server Schema
-- Optimiert für Power BI DirectQuery / Import
-- Daten: 2015-2025 (kombiniert aus Kaggle + WHR 2025)
-- ============================================================

USE [YourDatabaseName]; -- Datenbankname anpassen!
GO

-- ============================================================
-- SCHEMA erstellen (optional)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'whr')
BEGIN
    EXEC('CREATE SCHEMA whr');
END
GO

-- ============================================================
-- DIMENSION: Regionen
-- ============================================================
IF OBJECT_ID('whr.dim_region', 'U') IS NOT NULL
    DROP TABLE whr.dim_region;
GO

CREATE TABLE whr.dim_region (
    region_id INT IDENTITY(1,1) PRIMARY KEY,
    region_name NVARCHAR(100) NOT NULL UNIQUE
);
GO

INSERT INTO whr.dim_region (region_name) VALUES
    (N'Australia and New Zealand'),
    (N'Central and Eastern Europe'),
    (N'Eastern Asia'),
    (N'Latin America and Caribbean'),
    (N'Middle East and Northern Africa'),
    (N'North America'),
    (N'Southeastern Asia'),
    (N'Southern Asia'),
    (N'Sub-Saharan Africa'),
    (N'Western Europe');
GO

-- ============================================================
-- DIMENSION: Länder
-- ============================================================
IF OBJECT_ID('whr.dim_country', 'U') IS NOT NULL
    DROP TABLE whr.dim_country;
GO

CREATE TABLE whr.dim_country (
    country_id INT IDENTITY(1,1) PRIMARY KEY,
    country_name NVARCHAR(100) NOT NULL UNIQUE,
    region_id INT FOREIGN KEY REFERENCES whr.dim_region(region_id)
);
GO

-- ============================================================
-- DIMENSION: Zeit (für Power BI Zeitintelligenz)
-- ============================================================
IF OBJECT_ID('whr.dim_year', 'U') IS NOT NULL
    DROP TABLE whr.dim_year;
GO

CREATE TABLE whr.dim_year (
    year_id INT PRIMARY KEY,
    year_name NVARCHAR(4),
    decade NVARCHAR(10),
    is_current_year BIT DEFAULT 0
);
GO

INSERT INTO whr.dim_year (year_id, year_name, decade, is_current_year)
VALUES 
    (2015, '2015', '2010s', 0),
    (2016, '2016', '2010s', 0),
    (2017, '2017', '2010s', 0),
    (2018, '2018', '2010s', 0),
    (2019, '2019', '2010s', 0),
    (2020, '2020', '2020s', 0),
    (2021, '2021', '2020s', 0),
    (2022, '2022', '2020s', 0),
    (2023, '2023', '2020s', 0),
    (2024, '2024', '2020s', 0),
    (2025, '2025', '2020s', 1);
GO

-- ============================================================
-- FAKTEN: Happiness Scores
-- ============================================================
IF OBJECT_ID('whr.fact_happiness', 'U') IS NOT NULL
    DROP TABLE whr.fact_happiness;
GO

CREATE TABLE whr.fact_happiness (
    happiness_id INT IDENTITY(1,1) PRIMARY KEY,
    country_id INT FOREIGN KEY REFERENCES whr.dim_country(country_id),
    year_id INT FOREIGN KEY REFERENCES whr.dim_year(year_id),
    happiness_rank INT,
    happiness_score DECIMAL(5,3),
    gdp DECIMAL(10,6),
    social_support DECIMAL(10,6),
    life_expectancy DECIMAL(10,6),
    freedom DECIMAL(10,6),
    generosity DECIMAL(10,6),
    corruption DECIMAL(10,6),
    created_at DATETIME2 DEFAULT GETDATE(),
    CONSTRAINT UQ_country_year UNIQUE (country_id, year_id)
);
GO

-- ============================================================
-- INDIZES für Performance
-- ============================================================
CREATE NONCLUSTERED INDEX IX_fact_happiness_year 
    ON whr.fact_happiness(year_id);
CREATE NONCLUSTERED INDEX IX_fact_happiness_country 
    ON whr.fact_happiness(country_id);
CREATE NONCLUSTERED INDEX IX_fact_happiness_score 
    ON whr.fact_happiness(happiness_score DESC);
CREATE NONCLUSTERED INDEX IX_dim_country_region 
    ON whr.dim_country(region_id);
GO

-- ============================================================
-- VIEW: Denormalisierte Ansicht für Power BI (Haupttabelle)
-- ============================================================
IF OBJECT_ID('whr.v_happiness_report', 'V') IS NOT NULL
    DROP VIEW whr.v_happiness_report;
GO

CREATE VIEW whr.v_happiness_report AS
SELECT 
    f.happiness_id,
    y.year_id AS [Year],
    y.year_name AS [Year Name],
    y.decade AS [Decade],
    f.happiness_rank AS [Rank],
    c.country_name AS [Country],
    r.region_name AS [Region],
    f.happiness_score AS [Happiness Score],
    f.gdp AS [GDP per Capita],
    f.social_support AS [Social Support],
    f.life_expectancy AS [Life Expectancy],
    f.freedom AS [Freedom],
    f.generosity AS [Generosity],
    f.corruption AS [Corruption],
    -- Berechnete Spalten für Power BI
    CASE 
        WHEN f.happiness_score >= 6.5 THEN 'High'
        WHEN f.happiness_score >= 5.0 THEN 'Medium'
        ELSE 'Low'
    END AS [Happiness Category],
    -- Faktoren-Summe (ohne Dystopia)
    ISNULL(f.gdp, 0) + ISNULL(f.social_support, 0) + 
    ISNULL(f.life_expectancy, 0) + ISNULL(f.freedom, 0) + 
    ISNULL(f.generosity, 0) + ISNULL(f.corruption, 0) AS [Explained Factors Sum]
FROM whr.fact_happiness f
INNER JOIN whr.dim_country c ON f.country_id = c.country_id
LEFT JOIN whr.dim_region r ON c.region_id = r.region_id
INNER JOIN whr.dim_year y ON f.year_id = y.year_id;
GO

-- ============================================================
-- VIEW: Aktuelles Ranking (für KPI-Cards)
-- ============================================================
IF OBJECT_ID('whr.v_current_ranking', 'V') IS NOT NULL
    DROP VIEW whr.v_current_ranking;
GO

CREATE VIEW whr.v_current_ranking AS
SELECT 
    f.happiness_rank AS [Rank],
    c.country_name AS [Country],
    r.region_name AS [Region],
    f.happiness_score AS [Happiness Score],
    f.gdp AS [GDP per Capita],
    f.social_support AS [Social Support],
    f.freedom AS [Freedom]
FROM whr.fact_happiness f
INNER JOIN whr.dim_country c ON f.country_id = c.country_id
LEFT JOIN whr.dim_region r ON c.region_id = r.region_id
WHERE f.year_id = (SELECT MAX(year_id) FROM whr.fact_happiness);
GO

-- ============================================================
-- VIEW: Regionale Statistiken (für Balkendiagramme)
-- ============================================================
IF OBJECT_ID('whr.v_regional_stats', 'V') IS NOT NULL
    DROP VIEW whr.v_regional_stats;
GO

CREATE VIEW whr.v_regional_stats AS
SELECT 
    r.region_name AS [Region],
    y.year_id AS [Year],
    COUNT(*) AS [Country Count],
    ROUND(AVG(f.happiness_score), 3) AS [Avg Happiness Score],
    ROUND(AVG(f.gdp), 3) AS [Avg GDP],
    ROUND(AVG(f.social_support), 3) AS [Avg Social Support],
    ROUND(AVG(f.life_expectancy), 3) AS [Avg Life Expectancy],
    ROUND(AVG(f.freedom), 3) AS [Avg Freedom],
    MIN(f.happiness_score) AS [Min Score],
    MAX(f.happiness_score) AS [Max Score]
FROM whr.fact_happiness f
INNER JOIN whr.dim_country c ON f.country_id = c.country_id
INNER JOIN whr.dim_region r ON c.region_id = r.region_id
INNER JOIN whr.dim_year y ON f.year_id = y.year_id
GROUP BY r.region_name, y.year_id;
GO

-- ============================================================
-- VIEW: Länder-Trends mit YoY-Veränderung
-- ============================================================
IF OBJECT_ID('whr.v_country_trends', 'V') IS NOT NULL
    DROP VIEW whr.v_country_trends;
GO

CREATE VIEW whr.v_country_trends AS
SELECT 
    c.country_name AS [Country],
    r.region_name AS [Region],
    f.year_id AS [Year],
    f.happiness_score AS [Happiness Score],
    f.happiness_score - LAG(f.happiness_score) OVER (
        PARTITION BY c.country_id ORDER BY f.year_id
    ) AS [Score Change YoY],
    f.happiness_rank AS [Rank],
    f.happiness_rank - LAG(f.happiness_rank) OVER (
        PARTITION BY c.country_id ORDER BY f.year_id
    ) AS [Rank Change YoY]
FROM whr.fact_happiness f
INNER JOIN whr.dim_country c ON f.country_id = c.country_id
LEFT JOIN whr.dim_region r ON c.region_id = r.region_id;
GO

-- ============================================================
-- STORED PROCEDURE: Daten aus Staging importieren
-- ============================================================
IF OBJECT_ID('whr.sp_import_from_staging', 'P') IS NOT NULL
    DROP PROCEDURE whr.sp_import_from_staging;
GO

CREATE PROCEDURE whr.sp_import_from_staging
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Voraussetzung: Staging-Tabelle existiert mit CSV-Daten
    -- CREATE TABLE whr.staging_import (
    --     Country NVARCHAR(100),
    --     Year INT,
    --     Region NVARCHAR(100),
    --     [Happiness Rank] INT,
    --     [Happiness Score] DECIMAL(5,3),
    --     GDP DECIMAL(10,6),
    --     [Social Support] DECIMAL(10,6),
    --     [Life Expectancy] DECIMAL(10,6),
    --     Freedom DECIMAL(10,6),
    --     Generosity DECIMAL(10,6),
    --     Corruption DECIMAL(10,6)
    -- );
    
    -- 1. Länder einfügen
    INSERT INTO whr.dim_country (country_name, region_id)
    SELECT DISTINCT 
        s.Country,
        r.region_id
    FROM whr.staging_import s
    LEFT JOIN whr.dim_region r ON s.Region = r.region_name
    WHERE NOT EXISTS (
        SELECT 1 FROM whr.dim_country c WHERE c.country_name = s.Country
    );
    
    -- 2. Fakten einfügen/aktualisieren (MERGE)
    MERGE whr.fact_happiness AS target
    USING (
        SELECT 
            c.country_id,
            s.Year AS year_id,
            s.[Happiness Rank],
            s.[Happiness Score],
            s.GDP,
            s.[Social Support],
            s.[Life Expectancy],
            s.Freedom,
            s.Generosity,
            s.Corruption
        FROM whr.staging_import s
        INNER JOIN whr.dim_country c ON s.Country = c.country_name
    ) AS source
    ON target.country_id = source.country_id AND target.year_id = source.year_id
    WHEN MATCHED THEN
        UPDATE SET 
            happiness_rank = source.[Happiness Rank],
            happiness_score = source.[Happiness Score],
            gdp = source.GDP,
            social_support = source.[Social Support],
            life_expectancy = source.[Life Expectancy],
            freedom = source.Freedom,
            generosity = source.Generosity,
            corruption = source.Corruption
    WHEN NOT MATCHED THEN
        INSERT (country_id, year_id, happiness_rank, happiness_score, 
                gdp, social_support, life_expectancy, freedom, generosity, corruption)
        VALUES (source.country_id, source.year_id, source.[Happiness Rank], source.[Happiness Score],
                source.GDP, source.[Social Support], source.[Life Expectancy], 
                source.Freedom, source.Generosity, source.Corruption);
    
    -- 3. Staging-Tabelle leeren
    TRUNCATE TABLE whr.staging_import;
    
    PRINT 'Import completed successfully.';
END;
GO

-- ============================================================
-- DAX MEASURES für Power BI (als Kommentar/Referenz)
-- ============================================================
/*
-- Diese DAX-Measures können in Power BI erstellt werden:

-- Durchschnittlicher Happiness Score
Avg Happiness Score = AVERAGE('v_happiness_report'[Happiness Score])

-- Anzahl Länder
Country Count = DISTINCTCOUNT('v_happiness_report'[Country])

-- YoY Veränderung
Score Change YoY = 
VAR CurrentYear = MAX('v_happiness_report'[Year])
VAR PreviousYear = CurrentYear - 1
VAR CurrentScore = CALCULATE(AVERAGE('v_happiness_report'[Happiness Score]), 'v_happiness_report'[Year] = CurrentYear)
VAR PreviousScore = CALCULATE(AVERAGE('v_happiness_report'[Happiness Score]), 'v_happiness_report'[Year] = PreviousYear)
RETURN CurrentScore - PreviousScore

-- Top 10 Länder (aktuelles Jahr)
Top 10 Countries = 
TOPN(10, 
    FILTER('v_happiness_report', 'v_happiness_report'[Year] = MAX('v_happiness_report'[Year])),
    [Happiness Score], DESC
)

-- Korrelation GDP zu Happiness (für Scatter Plot)
-- In Power BI über X/Y-Achsen im Scatter Chart
*/

-- ============================================================
-- BERECHTIGUNGEN
-- ============================================================
-- GRANT SELECT ON SCHEMA::whr TO [PowerBIServiceAccount];
-- GRANT EXECUTE ON whr.sp_import_from_staging TO [ETLServiceAccount];

PRINT 'Schema whr erfolgreich erstellt!';
GO
