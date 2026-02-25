# Rainforest Dashboard — Design Document

**Datum:** 2026-02-25
**UC:** UC4 — Interaktive Datenvisualisierung
**URL:** rainforest.butscher.cloud

---

## Ziel

Interaktives Dashboard zur Visualisierung der Amazon-Entwaldung (2000–2024) mit
Zeitreihen, geografischer Karte, Biom-Vergleich und einfacher Trendprojektion.
Zeigt den Knowledge-Navigator-Workflow: KI findet Daten → Deepnote bereitet vor →
Supabase speichert → Dash visualisiert.

---

## Architektur

```
Deepnote (einmalig)
  ├── Notebook A: TerraBrasilis REST API → CSV → Supabase
  └── Notebook B: Shapefiles → GeoJSON → assets/

Supabase VPS (Schema: Rainforest)
  ├── dim_state
  ├── dim_biome
  └── fact_deforestation

Plotly Dash (Docker → rainforest.butscher.cloud)
  ├── data_loader.py   PostgREST API (Accept-Profile: Rainforest)
  ├── app.py           Layout + Callbacks
  └── assets/          style.css, prodes_states.geojson, raisg_territories.geojson
```

---

## Datenquellen

| Quelle | Inhalt | Format | Zugang |
|--------|--------|--------|--------|
| [TerraBrasilis PRODES](https://terrabrasilis.dpi.inpe.br) | Jährliche Entwaldung 2000–2024 nach Staat + Biom | REST API / CSV | Öffentlich |
| [TerraBrasilis Shapefile](https://terrabrasilis.dpi.inpe.br) | Entwaldungspolygone nach Bundesstaat | Shapefile | Öffentlich |
| [RAISG](https://www.raisg.org/en/maps/) | Indigene Territorien + Schutzgebiete | Shapefile | Öffentlich |

---

## Supabase DB-Schema

```sql
-- Schema anlegen
CREATE SCHEMA IF NOT EXISTS "Rainforest";

-- Bundesstaaten Brasiliens
CREATE TABLE "Rainforest".dim_state (
    state_id   SERIAL PRIMARY KEY,
    state_code CHAR(2)      NOT NULL,  -- z.B. "PA" (Pará)
    state_name VARCHAR(100) NOT NULL,
    region     VARCHAR(50)             -- Norte, Nordeste, …
);

-- Biome
CREATE TABLE "Rainforest".dim_biome (
    biome_id   SERIAL PRIMARY KEY,
    biome_name VARCHAR(100) NOT NULL   -- Amazônia, Cerrado, …
);

-- Fakt: jährliche Entwaldung (PRODES)
CREATE TABLE "Rainforest".fact_deforestation (
    id              SERIAL PRIMARY KEY,
    year            SMALLINT      NOT NULL,
    state_id        INT REFERENCES "Rainforest".dim_state(state_id),
    biome_id        INT REFERENCES "Rainforest".dim_biome(biome_id),
    area_km2        NUMERIC(10,2) NOT NULL,   -- gerodete Fläche im Jahr
    accumulated_km2 NUMERIC(12,2)             -- kumuliert ab 2000, berechnet in Deepnote
);
```

---

## Deepnote Notebooks

### Notebook A — Zeitreihendaten
1. TerraBrasilis REST API abfragen (PRODES, Biom Amazônia + alle Staaten)
2. Rohdaten mit pandas transformieren
3. dim_state und dim_biome befüllen
4. fact_deforestation befüllen (inkl. `accumulated_km2` als cumsum)
5. Verbindung via `psycopg2` oder `supabase-py` zu VPS-Supabase

### Notebook B — Geodaten
1. PRODES Shapefile von TerraBrasilis herunterladen
2. RAISG Shapefile herunterladen
3. Mit `geopandas` einlesen, vereinfachen (`.simplify()` für Performance)
4. Als GeoJSON exportieren → `assets/prodes_states.geojson` und `assets/raisg_territories.geojson`
5. GeoJSON-Dateien in den Dash-Container kopieren

---

## Dashboard Layout

### Filter-Bar
- Jahr (Dropdown, 2000–2024)
- Biom (Dropdown: Amazônia / Cerrado / Mata Atlântica / alle)
- Staat (Dropdown, multi-select optional)

### KPI-Cards (3 Stück)
| Card | Inhalt |
|------|--------|
| Gerodet (Jahr) | km² im gewählten Jahr + Δ zum Vorjahr in % |
| Kumuliert gesamt | km² seit 2000 |
| Schlimmster Staat | Name + km² im gewählten Jahr |

### Chart-Grid (2 Spalten)

| Links | Rechts |
|-------|--------|
| Zeitreihe (Linie) — km²/Jahr 2000–2024 | Dash-Leaflet Karte — Choropleth nach Staat |
| Top 5 / Flop 5 Staaten (Balken, horizontal) | Biom-Vergleich (grouped Bar) |
| Kumulativer Area-Chart (volle Breite) | |

### Simulations-Abschnitt (unterhalb Charts)

**Schieberegler:**
- Jährliche Änderungsrate: -10 % bis +10 % (default: Trend der letzten 5 Jahre)
- Zeithorizont: 2025 bis 2075

**Preset-Buttons:**
- `Trend fortschreiben` — lineare Extrapolation letzter 5 Jahre
- `Paris-kompatibel` — -10 %/Jahr ab 2025
- `Null 2030` — Brasilianisches Regierungsziel

**Ausgabe:**
- Projektions-Chart: historische Linie (durchgezogen) + Projektion (gestrichelt)
- Textbox: "Bei diesem Szenario: Verlust bis 2050 = X km² · Entspricht Y × Deutschland"

**Implementierung:** Rein clientseitig, pandas/numpy in Dash-Callback. Einfache lineare/exponentielle Extrapolation, keine externe API.

---

## Dash-Leaflet Karte

- **Base layer:** OpenStreetMap tiles
- **Layer 1:** PRODES Choropleth (GeoJSON) — Fläche nach Staat, farbkodiert
- **Layer 2:** RAISG indigene Territorien (GeoJSON) — als Toggle ein/ausblendbar
- **Tooltip:** Hover über Staat → Name + km² + % des Bioms
- **Callback:** Klick auf Staat → filtert Zeitreihe und Top/Flop-Chart

---

## Tech Stack

| Komponente | Library |
|------------|---------|
| Web App | Plotly Dash |
| Karte | dash-leaflet |
| Geodaten | geopandas |
| Charts | plotly.graph_objects |
| DB-Anbindung | requests + PostgREST (analog WHI-Dashboard) |
| Datenvorbereitung | pandas, numpy |
| Deployment | Docker + Gunicorn → VPS |

---

## Datei-Struktur

```
UC4_Interaktive_Datenvisualisierung/
  deepnote/
    01_data_acquisition.ipynb    TerraBrasilis API → Supabase
    02_geodata_prep.ipynb        Shapefiles → GeoJSON
  webapp/
    app.py                       Dash Layout + Callbacks
    data_loader.py               Supabase PostgREST (Accept-Profile: Rainforest)
    simulation.py                Projektions-Logik (numpy)
    requirements.txt
    Dockerfile
    docker-compose.yml
    assets/
      style.css
      prodes_states.geojson
      raisg_territories.geojson
  db/
    rainforest_schema.sql        CREATE TABLE Statements
  docs/
    plans/
      2026-02-25-rainforest-dashboard-design.md
```

---

## Abgrenzung / YAGNI

- **Kein** automatisches Daten-Update (einmalig via Deepnote reicht)
- **Keine** Phil-Integration in UC4 (kommt als UC04 separat)
- **Keine** CO₂/Biodiversitäts-Berechnung in der Simulation (zu komplex)
- **Keine** Authentifizierung (öffentliches Dashboard)
