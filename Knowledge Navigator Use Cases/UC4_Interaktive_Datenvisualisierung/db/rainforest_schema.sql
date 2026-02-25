-- db/rainforest_schema.sql
CREATE SCHEMA IF NOT EXISTS "Rainforest";

CREATE TABLE IF NOT EXISTS "Rainforest".dim_state (
    state_id   SERIAL PRIMARY KEY,
    state_code CHAR(2)       NOT NULL,
    state_name VARCHAR(100)  NOT NULL,
    region     VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS "Rainforest".dim_biome (
    biome_id   SERIAL PRIMARY KEY,
    biome_name VARCHAR(100)  NOT NULL
);

CREATE TABLE IF NOT EXISTS "Rainforest".fact_deforestation (
    id              SERIAL PRIMARY KEY,
    year            SMALLINT      NOT NULL,
    state_id        INT REFERENCES "Rainforest".dim_state(state_id),
    biome_id        INT REFERENCES "Rainforest".dim_biome(biome_id),
    area_km2        NUMERIC(10,2) NOT NULL,
    accumulated_km2 NUMERIC(12,2)
);

-- Allow anon read via PostgREST
GRANT USAGE  ON SCHEMA "Rainforest" TO anon;
GRANT SELECT ON ALL TABLES IN SCHEMA "Rainforest" TO anon;
