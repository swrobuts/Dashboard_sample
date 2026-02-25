# Rainforest Dashboard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an interactive Plotly Dash dashboard visualising Amazon deforestation (2000–2024) with a Dash-Leaflet map, trend simulation sliders, and deployment to rainforest.butscher.cloud.

**Architecture:** Deepnote notebooks pull data from the TerraBrasilis REST API and shapefiles, transform with pandas/geopandas, and load into a `Rainforest` schema on the VPS Supabase instance. A Plotly Dash app reads from Supabase via PostgREST (same pattern as the World Happiness Dashboard) and serves charts + a Dash-Leaflet choropleth map. Everything ships as a single Docker container.

**Tech Stack:** Python 3.11, Plotly Dash, dash-leaflet, geopandas, pandas, numpy, requests (PostgREST), psycopg2, Gunicorn, Docker.

**Reference project:** `../../../Visualisierungen/WorldHappiness/` — study `data_loader.py` and `app.py` before starting. The Supabase connection pattern (`Accept-Profile` header, `lru_cache`) is identical.

**Working directory for all webapp tasks:** `Knowledge Navigator Use Cases/UC4_Interaktive_Datenvisualisierung/webapp/`

---

## Task 1: DB Schema — Create and apply to Supabase

**Files:**
- Create: `db/rainforest_schema.sql`

**Step 1: Create the SQL file**

```sql
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
```

**Step 2: Apply to Supabase**

Open the Supabase dashboard at `https://supabase.butscher.cloud` → SQL Editor → paste and run.

**Step 3: Verify**

In Supabase SQL Editor run:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'Rainforest';
```
Expected: 3 rows — `dim_state`, `dim_biome`, `fact_deforestation`

**Step 4: Commit**

```bash
git add db/rainforest_schema.sql
git commit -m "feat(db): Rainforest schema — dim_state, dim_biome, fact_deforestation"
```

---

## Task 2: Deepnote — Data Acquisition (TerraBrasilis → Supabase)

**Files:**
- Create: `deepnote/01_data_acquisition.ipynb`

**Context:** TerraBrasilis exposes a GeoServer WFS and a REST/dashboard API. The simplest reliable endpoint for PRODES annual data by state is:
`http://terrabrasilis.dpi.inpe.br/geoserver/prodes-amazon-nb/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=prodes-amazon-nb:yearly_deforestation_biome&outputFormat=application/json`

Alternatively use the dashboard CSV export: download from `https://terrabrasilis.dpi.inpe.br/en/download/` (Prodes Amazon, yearly, all states).

**Step 1: Create the notebook with this structure**

Cell 1 — Imports:
```python
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os

SUPABASE_HOST = "supabase.butscher.cloud"
SUPABASE_DB   = "postgres"
SUPABASE_USER = "postgres"
SUPABASE_PASS = os.environ["SUPABASE_DB_PASSWORD"]  # set in Deepnote env vars
SUPABASE_PORT = 5432
```

Cell 2 — Fetch PRODES data:
```python
# Download PRODES Amazon yearly data via WFS
url = (
    "http://terrabrasilis.dpi.inpe.br/geoserver/prodes-amazon-nb/ows"
    "?service=WFS&version=1.0.0&request=GetFeature"
    "&typeName=prodes-amazon-nb:yearly_deforestation_biome"
    "&outputFormat=application/json"
)
resp = requests.get(url, timeout=60)
resp.raise_for_status()
features = resp.json()["features"]
rows = [f["properties"] for f in features]
df_raw = pd.DataFrame(rows)
print(df_raw.columns.tolist())
print(df_raw.head())
```

Cell 3 — Inspect and map columns (adjust column names after seeing actual output):
```python
# Expected columns (verify after running Cell 2):
# year, state, biome, area (km²)
# Rename to our schema names
df = df_raw.rename(columns={
    "ano":    "year",       # adjust if different
    "estado": "state_name",
    "bioma":  "biome_name",
    "area":   "area_km2",
}).copy()

df["year"]      = df["year"].astype(int)
df["area_km2"]  = df["area_km2"].astype(float).round(2)
df = df[["year", "state_name", "biome_name", "area_km2"]].dropna()
print(f"{len(df)} rows, years {df.year.min()}–{df.year.max()}")
```

Cell 4 — Calculate cumulative area per state:
```python
df = df.sort_values(["state_name", "biome_name", "year"])
df["accumulated_km2"] = (
    df.groupby(["state_name", "biome_name"])["area_km2"]
    .cumsum()
    .round(2)
)
```

Cell 5 — Load into Supabase:
```python
conn = psycopg2.connect(
    host=SUPABASE_HOST, dbname=SUPABASE_DB,
    user=SUPABASE_USER, password=SUPABASE_PASS, port=SUPABASE_PORT
)
cur = conn.cursor()

# Insert dim_state
states = df["state_name"].unique()
state_map = {}  # name → id
for s in states:
    cur.execute(
        'INSERT INTO "Rainforest".dim_state (state_code, state_name) '
        'VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING state_id',
        (s[:2].upper(), s)
    )
    row = cur.fetchone()
    if row:
        state_map[s] = row[0]

# Re-fetch IDs for any that already existed
cur.execute('SELECT state_id, state_name FROM "Rainforest".dim_state')
for sid, sname in cur.fetchall():
    state_map[sname] = sid

# Insert dim_biome
biomes = df["biome_name"].unique()
biome_map = {}
for b in biomes:
    cur.execute(
        'INSERT INTO "Rainforest".dim_biome (biome_name) '
        'VALUES (%s) ON CONFLICT DO NOTHING RETURNING biome_id',
        (b,)
    )
    row = cur.fetchone()
    if row:
        biome_map[b] = row[0]
cur.execute('SELECT biome_id, biome_name FROM "Rainforest".dim_biome')
for bid, bname in cur.fetchall():
    biome_map[bname] = bid

# Insert fact_deforestation
records = [
    (int(r.year), state_map[r.state_name], biome_map[r.biome_name],
     float(r.area_km2), float(r.accumulated_km2))
    for r in df.itertuples()
    if r.state_name in state_map and r.biome_name in biome_map
]
execute_values(
    cur,
    'INSERT INTO "Rainforest".fact_deforestation '
    '(year, state_id, biome_id, area_km2, accumulated_km2) VALUES %s',
    records
)
conn.commit()
conn.close()
print(f"✓ {len(records)} rows inserted into fact_deforestation")
```

**Step 2: Run all cells in Deepnote**

Expected output of last cell: `✓ N rows inserted into fact_deforestation` (N should be ~500–1000 depending on API coverage)

**Step 3: Verify in Supabase SQL Editor**

```sql
SELECT year, COUNT(*) FROM "Rainforest".fact_deforestation
GROUP BY year ORDER BY year;
```
Expected: rows for each year 2000–2024.

**Step 4: Commit notebook**

```bash
git add deepnote/01_data_acquisition.ipynb
git commit -m "feat(deepnote): data acquisition — TerraBrasilis PRODES → Supabase"
```

---

## Task 3: Deepnote — Geodata Prep (Shapefiles → GeoJSON)

**Files:**
- Create: `deepnote/02_geodata_prep.ipynb`
- Output: `webapp/assets/prodes_states.geojson`
- Output: `webapp/assets/raisg_territories.geojson`

**Step 1: Create notebook — imports and download**

Cell 1:
```python
import geopandas as gpd
import requests, zipfile, io, os

os.makedirs("../webapp/assets", exist_ok=True)
```

Cell 2 — Brazilian state boundaries (IBGE):
```python
# Official Brazilian state boundaries from IBGE (public domain)
url = "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2022/Brasil/BR/BR_UF_2022.zip"
resp = requests.get(url, timeout=120)
with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
    z.extractall("shapefiles/ibge_states/")

gdf_states = gpd.read_file("shapefiles/ibge_states/")
gdf_states = gdf_states.to_crs("EPSG:4326")
print(gdf_states.columns.tolist())
print(f"{len(gdf_states)} states")
```

Cell 3 — Simplify and export states:
```python
# Simplify geometry for web performance (tolerance in degrees ~1km)
gdf_states["geometry"] = gdf_states["geometry"].simplify(0.01, preserve_topology=True)

# Keep only relevant columns
gdf_states = gdf_states[["SIGLA_UF", "NM_UF", "geometry"]].rename(columns={
    "SIGLA_UF": "state_code",
    "NM_UF":    "state_name"
})

gdf_states.to_file("../webapp/assets/prodes_states.geojson", driver="GeoJSON")
print(f"✓ prodes_states.geojson written ({len(gdf_states)} features)")
```

Cell 4 — RAISG indigenous territories:
```python
# RAISG provides shapefiles via their website — download manually if needed
# Fallback: use the GFW/UNEP-WCMC protected areas dataset (public)
# Here we use the RAISG 2021 dataset URL (check raisg.org/en/maps/ for latest)
url_raisg = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/brazil-states.geojson"
# NOTE: Replace with actual RAISG shapefile URL from https://www.raisg.org/en/maps/
# If manual download: place file at shapefiles/raisg/raisg_territories.shp

try:
    gdf_raisg = gpd.read_file("shapefiles/raisg/raisg_territories.shp")
    gdf_raisg = gdf_raisg.to_crs("EPSG:4326")
    gdf_raisg["geometry"] = gdf_raisg["geometry"].simplify(0.01, preserve_topology=True)
    gdf_raisg.to_file("../webapp/assets/raisg_territories.geojson", driver="GeoJSON")
    print(f"✓ raisg_territories.geojson written ({len(gdf_raisg)} features)")
except Exception as e:
    print(f"RAISG shapefile not found — download manually from raisg.org: {e}")
    # Create empty placeholder so app still loads
    import json
    with open("../webapp/assets/raisg_territories.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": []}, f)
    print("✓ Empty placeholder written — replace with real RAISG data")
```

**Step 2: Run all cells**

Expected: two `.geojson` files in `webapp/assets/`

**Step 3: Check file sizes**

Files should be < 5 MB each (simplification ensures this). If larger, increase `simplify()` tolerance to `0.05`.

**Step 4: Commit**

```bash
git add deepnote/02_geodata_prep.ipynb webapp/assets/prodes_states.geojson webapp/assets/raisg_territories.geojson
git commit -m "feat(geodata): IBGE state boundaries + RAISG territories → GeoJSON assets"
```

---

## Task 4: Webapp Scaffold

**Files:**
- Create: `webapp/requirements.txt`
- Create: `webapp/Dockerfile`
- Create: `webapp/docker-compose.yml`
- Create: `webapp/.env.example`
- Create: `webapp/assets/style.css` (empty placeholder)
- Create: `webapp/data_loader.py` (stub)
- Create: `webapp/simulation.py` (stub)
- Create: `webapp/app.py` (minimal, runnable)

**Step 1: Create requirements.txt**

```
dash==2.17.1
dash-leaflet==1.0.15
plotly==5.22.0
pandas==2.2.2
numpy==1.26.4
requests==2.32.3
python-dotenv==1.0.1
gunicorn==22.0.0
geopandas==0.14.4
```

**Step 2: Create .env.example**

```bash
# Supabase VPS
SUPABASE_URL=https://supabase.butscher.cloud
SUPABASE_KEY=your_anon_key_here
```

**Step 3: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050
CMD ["gunicorn", "app:server", "-b", "0.0.0.0:8050", "--workers", "2", "--timeout", "120"]
```

**Step 4: Create docker-compose.yml**

```yaml
services:
  rainforest:
    build: .
    restart: unless-stopped
    env_file: .env
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.rainforest.rule=Host(`rainforest.butscher.cloud`)"
      - "traefik.http.routers.rainforest.entrypoints=websecure"
      - "traefik.http.routers.rainforest.tls.certresolver=letsencrypt"
      - "traefik.http.services.rainforest.loadbalancer.server.port=8050"
    networks:
      - traefik_default

networks:
  traefik_default:
    external: true
```

**Step 5: Create stub app.py (just verifies Dash runs)**

```python
import dash
from dash import html

app = dash.Dash(__name__, title="Amazon Rainforest Dashboard")
server = app.server

app.layout = html.Div("Loading...")

if __name__ == "__main__":
    app.run(debug=True, port=8050)
```

**Step 6: Create stub data_loader.py**

```python
# Stub — implemented in Task 5
def load_deforestation_data():
    raise NotImplementedError
```

**Step 7: Create stub simulation.py**

```python
# Stub — implemented in Task 10
def project_deforestation(df, rate_pct_per_year, horizon_year):
    raise NotImplementedError
```

**Step 8: Create empty assets/style.css**

```css
/* Styles added in Task 6 */
```

**Step 9: Verify app starts**

```bash
cd webapp
pip install -r requirements.txt
python app.py
```

Expected: `Dash is running on http://127.0.0.1:8050/` — open browser, see "Loading..."

**Step 10: Commit**

```bash
git add webapp/
git commit -m "feat(webapp): scaffold — Dockerfile, requirements, stub app.py"
```

---

## Task 5: data_loader.py — Supabase PostgREST

**Files:**
- Modify: `webapp/data_loader.py`

**Context:** Identical pattern to `../../../Visualisierungen/WorldHappiness/data_loader.py`. Uses `requests` + `Accept-Profile` header to select the `Rainforest` schema.

**Step 1: Write test first**

Create `webapp/test_data_loader.py`:
```python
"""Quick smoke test — requires .env with real Supabase credentials."""
import os
from dotenv import load_dotenv
load_dotenv()

def test_load_returns_dataframe():
    from data_loader import load_deforestation_data
    df = load_deforestation_data()
    assert len(df) > 0, "No rows returned"
    assert "year" in df.columns
    assert "state_name" in df.columns
    assert "biome_name" in df.columns
    assert "area_km2" in df.columns
    print(f"✓ {len(df)} rows, years {df.year.min()}–{df.year.max()}")

if __name__ == "__main__":
    test_load_returns_dataframe()
    print("All tests passed")
```

**Step 2: Run test — expect failure**

```bash
cd webapp && python test_data_loader.py
```
Expected: `NotImplementedError`

**Step 3: Implement data_loader.py**

```python
"""
Rainforest Dashboard — Supabase Data Loader
Connects via PostgREST API with Accept-Profile: Rainforest header.
"""
import os
import requests
import pandas as pd
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://supabase.butscher.cloud")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SCHEMA = "Rainforest"


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept-Profile": SCHEMA,
        "Content-Type": "application/json",
    }


def _fetch(table: str, params: dict = None) -> pd.DataFrame:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=_headers(), params=params or {})
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


@lru_cache(maxsize=1)
def load_states() -> pd.DataFrame:
    return _fetch("dim_state")


@lru_cache(maxsize=1)
def load_biomes() -> pd.DataFrame:
    return _fetch("dim_biome")


@lru_cache(maxsize=1)
def load_deforestation_data() -> pd.DataFrame:
    facts = _fetch("fact_deforestation", {"order": "year.asc"})
    states = load_states()
    biomes = load_biomes()
    df = (
        facts
        .merge(states[["state_id", "state_name", "region"]], on="state_id", how="left")
        .merge(biomes[["biome_id", "biome_name"]], on="biome_id", how="left")
    )
    df["year"] = df["year"].astype(int)
    df["area_km2"] = df["area_km2"].astype(float)
    df["accumulated_km2"] = df["accumulated_km2"].astype(float)
    return df


def get_years() -> list[int]:
    return sorted(load_deforestation_data()["year"].unique().tolist())


def get_biomes() -> list[str]:
    return sorted(load_deforestation_data()["biome_name"].dropna().unique().tolist())


def get_states() -> list[str]:
    return sorted(load_deforestation_data()["state_name"].dropna().unique().tolist())


def clear_cache():
    load_states.cache_clear()
    load_biomes.cache_clear()
    load_deforestation_data.cache_clear()
```

**Step 4: Run test — expect pass**

```bash
cd webapp && python test_data_loader.py
```
Expected: `✓ N rows, years 2000–2024` then `All tests passed`

**Step 5: Commit**

```bash
git add webapp/data_loader.py webapp/test_data_loader.py
git commit -m "feat(data): data_loader.py — PostgREST Supabase connection with lru_cache"
```

---

## Task 6: app.py — Layout (header, filter-bar, KPI-cards)

**Files:**
- Modify: `webapp/app.py`
- Modify: `webapp/assets/style.css`

**Step 1: Replace app.py layout with full shell**

```python
"""
Amazon Rainforest Deforestation Dashboard
"""
import dash
from dash import dcc, html, Input, Output, callback
import plotly.graph_objects as go
import pandas as pd
import numpy as np

import dash_leaflet as dl

from data_loader import (
    load_deforestation_data,
    get_years, get_biomes, get_states,
)
from simulation import project_deforestation

# ── App init ────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    title="Amazon Rainforest Dashboard",
    update_title=None,
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap"
    ],
    suppress_callback_exceptions=True,
)
server = app.server

# ── Data ─────────────────────────────────────────────────────────────────────
df = load_deforestation_data()
YEARS  = get_years()
BIOMES = get_biomes()
STATES = get_states()
LATEST = max(YEARS)

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN_DARK   = "#1a3a2a"
GREEN_MED    = "#2d6a4f"
GREEN_LIGHT  = "#52b788"
RED_DARK     = "#9b2226"
RED_MED      = "#ae2012"
NEUTRAL      = "#f5f5f0"
TEXT         = "#1a1a1a"
TEXT_MUTED   = "#666"
BORDER       = "#e0e0e0"

# ── Layout ───────────────────────────────────────────────────────────────────
def make_kpi_card(title, value_id, subtitle_id):
    return html.Div([
        html.Div(title, className="kpi-title"),
        html.Div("—", id=value_id, className="kpi-value"),
        html.Div("", id=subtitle_id, className="kpi-subtitle"),
    ], className="kpi-card")


app.layout = html.Div([

    # Header
    html.Header([
        html.Div([
            html.H1("Amazon Rainforest"),
            html.P("Deforestation Monitor · INPE/PRODES 2000–2024"),
        ], className="header-text"),
        html.Div([
            html.Span("Datenquelle: "),
            html.A("TerraBrasilis / INPE", href="https://terrabrasilis.dpi.inpe.br", target="_blank"),
        ], className="header-source"),
    ], className="header"),

    # Filter bar
    html.Div([
        html.Div([
            html.Label("Jahr"),
            dcc.Dropdown(
                id="filter-year",
                options=[{"label": str(y), "value": y} for y in YEARS],
                value=LATEST, clearable=False,
            ),
        ], className="filter-item"),
        html.Div([
            html.Label("Biom"),
            dcc.Dropdown(
                id="filter-biome",
                options=[{"label": "Alle Biome", "value": "all"}] +
                        [{"label": b, "value": b} for b in BIOMES],
                value="all", clearable=False,
            ),
        ], className="filter-item"),
        html.Div([
            html.Label("Staat"),
            dcc.Dropdown(
                id="filter-state",
                options=[{"label": "Alle Staaten", "value": "all"}] +
                        [{"label": s, "value": s} for s in STATES],
                value="all", clearable=False,
            ),
        ], className="filter-item"),
    ], className="filter-bar"),

    # KPI cards
    html.Div([
        make_kpi_card("Gerodet (Jahr)", "kpi-year-val", "kpi-year-sub"),
        make_kpi_card("Kumuliert seit 2000", "kpi-total-val", "kpi-total-sub"),
        make_kpi_card("Schlimmster Staat", "kpi-worst-val", "kpi-worst-sub"),
    ], className="kpi-row"),

    # Charts grid — added in Task 7–9
    html.Div(id="charts-grid", className="charts-grid"),

    # Simulation — added in Task 10
    html.Div(id="simulation-section"),

    # Footer
    html.Footer([
        html.Span("Daten: INPE PRODES via TerraBrasilis · RAISG (indigene Territorien)"),
    ], className="footer"),

], className="dashboard")


if __name__ == "__main__":
    app.run(debug=True, port=8050)
```

**Step 2: Add base CSS to assets/style.css**

```css
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Inter', sans-serif;
    background: #f5f5f0;
    color: #1a1a1a;
    font-size: 15px;
}

.dashboard { max-width: 1400px; margin: 0 auto; padding: 0 24px 48px; }

/* Header */
.header {
    display: flex; justify-content: space-between; align-items: flex-end;
    padding: 32px 0 20px;
    border-bottom: 2px solid #2d6a4f;
    margin-bottom: 20px;
}
.header h1 { font-size: 28px; font-weight: 600; color: #1a3a2a; }
.header p  { font-size: 13px; color: #666; margin-top: 4px; }
.header-source { font-size: 12px; color: #888; }
.header-source a { color: #2d6a4f; text-decoration: none; }

/* Filter bar */
.filter-bar {
    display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap;
}
.filter-item { flex: 1; min-width: 160px; }
.filter-item label { font-size: 11px; font-weight: 500; color: #666;
    text-transform: uppercase; letter-spacing: 0.05em; display: block;
    margin-bottom: 4px; }

/* KPI cards */
.kpi-row {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 16px; margin-bottom: 20px;
}
.kpi-card {
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    padding: 20px 24px;
}
.kpi-title   { font-size: 11px; font-weight: 500; color: #666;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
.kpi-value   { font-size: 32px; font-weight: 300; color: #1a3a2a; }
.kpi-subtitle { font-size: 12px; color: #888; margin-top: 4px; }

/* Charts grid */
.charts-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 16px; margin-bottom: 20px;
}
.chart-card {
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    padding: 20px;
}
.chart-card h3 { font-size: 13px; font-weight: 500; color: #1a1a1a;
    margin-bottom: 4px; }
.chart-card .chart-sub { font-size: 11px; color: #888; margin-bottom: 12px; }
.chart-card.full-width { grid-column: 1 / -1; }

/* Simulation */
.simulation-section {
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    padding: 24px; margin-bottom: 20px;
}
.simulation-section h2 { font-size: 16px; font-weight: 500;
    color: #1a3a2a; margin-bottom: 16px; }
.sim-controls { display: flex; gap: 32px; flex-wrap: wrap; margin-bottom: 16px; }
.sim-slider { flex: 1; min-width: 200px; }
.sim-slider label { font-size: 11px; font-weight: 500; color: #666;
    text-transform: uppercase; letter-spacing: 0.05em; display: block;
    margin-bottom: 8px; }
.sim-presets { display: flex; gap: 8px; margin-bottom: 20px; }
.sim-presets button {
    padding: 6px 14px; border-radius: 16px; border: 1px solid #2d6a4f;
    background: #fff; color: #2d6a4f; font-size: 12px; cursor: pointer;
}
.sim-presets button:hover { background: #2d6a4f; color: #fff; }
.sim-result {
    background: #f0f7f4; border-radius: 6px; padding: 12px 16px;
    font-size: 13px; color: #1a3a2a; margin-bottom: 16px;
}

/* Footer */
.footer { border-top: 1px solid #e0e0e0; padding: 16px 0;
    font-size: 11px; color: #999; }

/* Responsive */
@media (max-width: 768px) {
    .kpi-row { grid-template-columns: 1fr; }
    .charts-grid { grid-template-columns: 1fr; }
    .chart-card.full-width { grid-column: 1; }
}
```

**Step 3: Verify app starts without error**

```bash
cd webapp && python app.py
```
Expected: App loads at `http://127.0.0.1:8050`, shows header + filter bar + 3 empty KPI cards.

**Step 4: Commit**

```bash
git add webapp/app.py webapp/assets/style.css
git commit -m "feat(ui): dashboard shell — header, filter-bar, KPI-cards, CSS"
```

---

## Task 7: Callbacks — KPI cards + Chart data

**Files:**
- Modify: `webapp/app.py` (add callbacks section after layout)

**Step 1: Add KPI callback after the layout block in app.py**

```python
# ── Helpers ──────────────────────────────────────────────────────────────────
def filter_df(year, biome, state):
    d = df.copy()
    d = d[d["year"] == year]
    if biome != "all":
        d = d[d["biome_name"] == biome]
    if state != "all":
        d = d[d["state_name"] == state]
    return d


# ── KPI Callback ─────────────────────────────────────────────────────────────
@callback(
    Output("kpi-year-val", "children"),
    Output("kpi-year-sub", "children"),
    Output("kpi-total-val", "children"),
    Output("kpi-total-sub", "children"),
    Output("kpi-worst-val", "children"),
    Output("kpi-worst-sub", "children"),
    Input("filter-year", "value"),
    Input("filter-biome", "value"),
    Input("filter-state", "value"),
)
def update_kpis(year, biome, state):
    d = filter_df(year, biome, state)

    # Gerodet aktuelles Jahr
    area_year = d["area_km2"].sum()
    prev = filter_df(year - 1, biome, state)["area_km2"].sum() if year > min(YEARS) else None
    delta = f"{'↓' if prev and area_year < prev else '↑'} {abs(area_year - prev):,.0f} km² zum Vorjahr" if prev else ""
    kpi_year_val = f"{area_year:,.0f} km²"

    # Kumuliert: use fact_deforestation accumulated for all years up to selected
    d_accum = df.copy()
    if biome != "all":
        d_accum = d_accum[d_accum["biome_name"] == biome]
    if state != "all":
        d_accum = d_accum[d_accum["state_name"] == state]
    total = d_accum[d_accum["year"] <= year]["area_km2"].sum()
    kpi_total_val = f"{total:,.0f} km²"
    kpi_total_sub = f"≈ {total / 357_114:.1f}× Deutschland" if total > 0 else ""

    # Schlimmster Staat
    if state == "all" and len(d) > 0:
        worst = d.groupby("state_name")["area_km2"].sum().idxmax()
        worst_val = d[d["state_name"] == worst]["area_km2"].sum()
        kpi_worst_val = worst
        kpi_worst_sub = f"{worst_val:,.0f} km²"
    else:
        kpi_worst_val = state if state != "all" else "—"
        kpi_worst_sub = f"{area_year:,.0f} km²" if state != "all" else ""

    return kpi_year_val, delta, kpi_total_val, kpi_total_sub, kpi_worst_val, kpi_worst_sub
```

**Step 2: Verify**

Run app, change year filter. KPI numbers should update.

**Step 3: Commit**

```bash
git add webapp/app.py
git commit -m "feat(callbacks): KPI cards — gerodet, kumuliert, schlimmster Staat"
```

---

## Task 8: Charts — Zeitreihe, Top/Flop, Biom-Vergleich, Area-Chart

**Files:**
- Modify: `webapp/app.py` (replace `html.Div(id="charts-grid")` with actual charts + callback)

**Step 1: Replace the charts-grid placeholder in the layout**

Replace `html.Div(id="charts-grid", className="charts-grid")` with:

```python
    html.Div([
        # Zeitreihe
        html.Div([
            html.H3("Jährliche Entwaldung"),
            html.Div("km² pro Jahr", className="chart-sub"),
            dcc.Graph(id="chart-timeseries", config={"displayModeBar": False}),
        ], className="chart-card"),

        # Top/Flop Staaten
        html.Div([
            html.H3("Top 5 Staaten"),
            html.Div(id="chart-topflop-sub", className="chart-sub"),
            dcc.Graph(id="chart-topflop", config={"displayModeBar": False}),
        ], className="chart-card"),

        # Biom-Vergleich
        html.Div([
            html.H3("Biom-Vergleich"),
            html.Div("Entwaldung nach Biom", className="chart-sub"),
            dcc.Graph(id="chart-biome", config={"displayModeBar": False}),
        ], className="chart-card"),

        # Kumulativer Area-Chart (volle Breite)
        html.Div([
            html.H3("Kumulativer Verlust"),
            html.Div("Aufgestapelt nach Biom, 2000–heute", className="chart-sub"),
            dcc.Graph(id="chart-cumulative", config={"displayModeBar": False}),
        ], className="chart-card full-width"),

    ], className="charts-grid"),
```

**Step 2: Add charts callback after KPI callback**

```python
CHART_LAYOUT = dict(
    paper_bgcolor="white", plot_bgcolor="white",
    font=dict(family="Inter", size=12, color=TEXT),
    margin=dict(l=40, r=20, t=10, b=40),
    showlegend=False,
)

GREEN_SCALE = [[0, "#e8f5e9"], [0.5, "#52b788"], [1, "#1a3a2a"]]


@callback(
    Output("chart-timeseries", "figure"),
    Output("chart-topflop", "figure"),
    Output("chart-topflop-sub", "children"),
    Output("chart-biome", "figure"),
    Output("chart-cumulative", "figure"),
    Input("filter-year", "value"),
    Input("filter-biome", "value"),
    Input("filter-state", "value"),
)
def update_charts(year, biome, state):
    # ── Filter for selected biome/state across ALL years ──────────────────
    d_all = df.copy()
    if biome != "all":
        d_all = d_all[d_all["biome_name"] == biome]
    if state != "all":
        d_all = d_all[d_all["state_name"] == state]

    # ── Zeitreihe ──────────────────────────────────────────────────────────
    ts = d_all.groupby("year")["area_km2"].sum().reset_index()
    fig_ts = go.Figure(go.Scatter(
        x=ts["year"], y=ts["area_km2"],
        mode="lines+markers",
        line=dict(color=GREEN_MED, width=2),
        marker=dict(size=5),
        fill="tozeroy", fillcolor="rgba(82,183,136,0.15)",
        hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
    ))
    fig_ts.update_layout(**CHART_LAYOUT, yaxis_title="km²", xaxis_title="Jahr")

    # ── Top 5 Staaten im gewählten Jahr ────────────────────────────────────
    d_year = filter_df(year, biome, state)
    by_state = d_year.groupby("state_name")["area_km2"].sum().sort_values(ascending=False)
    top5 = by_state.head(5)
    fig_top = go.Figure(go.Bar(
        y=top5.index, x=top5.values, orientation="h",
        marker_color=RED_MED,
        hovertemplate="%{y}: %{x:,.0f} km²<extra></extra>",
    ))
    fig_top.update_layout(**CHART_LAYOUT, xaxis_title="km²")
    topflop_sub = f"Meiste Entwaldung · {year}"

    # ── Biom-Vergleich ────────────────────────────────────────────────────
    biome_data = d_year.groupby("biome_name")["area_km2"].sum().sort_values(ascending=False)
    fig_biome = go.Figure(go.Bar(
        x=biome_data.index, y=biome_data.values,
        marker_color=GREEN_MED,
        hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
    ))
    fig_biome.update_layout(**CHART_LAYOUT, yaxis_title="km²")

    # ── Kumulativer Area-Chart ────────────────────────────────────────────
    pivot = d_all.groupby(["year", "biome_name"])["area_km2"].sum().unstack(fill_value=0)
    pivot_cumsum = pivot.cumsum()
    colors = [GREEN_DARK, GREEN_MED, GREEN_LIGHT, "#74c69d", "#b7e4c7", "#d8f3dc"]
    fig_cum = go.Figure()
    for i, col in enumerate(pivot_cumsum.columns):
        fig_cum.add_trace(go.Scatter(
            x=pivot_cumsum.index, y=pivot_cumsum[col],
            name=col, mode="lines",
            stackgroup="one",
            line=dict(color=colors[i % len(colors)], width=0.5),
            fillcolor=colors[i % len(colors)],
            hovertemplate=f"{col}: %{{y:,.0f}} km²<extra></extra>",
        ))
    fig_cum.update_layout(**CHART_LAYOUT, showlegend=True,
                          yaxis_title="km² (kumuliert)", xaxis_title="Jahr",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02))

    return fig_ts, fig_top, topflop_sub, fig_biome, fig_cum
```

**Step 3: Verify all 4 charts render**

Run app, check all charts show data. Change filters — charts should update.

**Step 4: Commit**

```bash
git add webapp/app.py
git commit -m "feat(charts): Zeitreihe, Top5-Staaten, Biom-Vergleich, kumulativer Area-Chart"
```

---

## Task 9: Dash-Leaflet Map

**Files:**
- Modify: `webapp/app.py`
- Requires: `webapp/assets/prodes_states.geojson` (from Task 3)
- Requires: `webapp/assets/raisg_territories.geojson` (from Task 3)

**Step 1: Load GeoJSON at startup (add after `df = load_deforestation_data()`)**

```python
import json

with open("assets/prodes_states.geojson") as f:
    STATES_GEO = json.load(f)

with open("assets/raisg_territories.geojson") as f:
    RAISG_GEO = json.load(f)
```

**Step 2: Replace the Zeitreihe chart-card in the layout grid (add map as second item)**

Add the map as the second chart card (after Zeitreihe, before Top/Flop):

```python
        # Leaflet Map
        html.Div([
            html.H3("Entwaldung nach Bundesstaat"),
            html.Div([
                html.Label("RAISG-Territorien anzeigen", style={"fontSize": "12px"}),
                dcc.Checklist(
                    id="toggle-raisg",
                    options=[{"label": " Indigene Territorien", "value": "show"}],
                    value=[],
                    style={"display": "inline-block", "marginLeft": "8px", "fontSize": "12px"},
                ),
            ], className="chart-sub"),
            dl.Map(
                id="map",
                center=[-5, -55], zoom=4,
                style={"height": "380px", "borderRadius": "6px"},
                children=[
                    dl.TileLayer(url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"),
                    dl.GeoJSON(
                        id="layer-states",
                        data=STATES_GEO,
                        options=dict(style=dict(weight=1, color="#fff", fillOpacity=0.7)),
                        hoverStyle=dict(weight=2, color="#333"),
                        zoomToBounds=True,
                    ),
                    dl.GeoJSON(
                        id="layer-raisg",
                        data={"type": "FeatureCollection", "features": []},
                        options=dict(style=dict(
                            weight=1, color="#e76f51", fillColor="#e76f51", fillOpacity=0.25
                        )),
                    ),
                ],
            ),
        ], className="chart-card"),
```

**Step 3: Add map callbacks**

```python
@callback(
    Output("layer-states", "hideout"),
    Output("layer-states", "options"),
    Input("filter-year", "value"),
    Input("filter-biome", "value"),
)
def update_map_colors(year, biome):
    d = df[df["year"] == year]
    if biome != "all":
        d = d[d["biome_name"] == biome]
    by_state = d.groupby("state_name")["area_km2"].sum().to_dict()
    max_val = max(by_state.values()) if by_state else 1

    # Pass data as hideout dict (accessible in clientside colorscale if needed)
    # For server-side coloring, use style_handle via options
    hideout = {"colorscale": ["#e8f5e9", "#52b788", "#1a3a2a"],
               "classes": [0, max_val * 0.25, max_val * 0.5, max_val * 0.75, max_val],
               "style": {"weight": 1, "color": "white", "fillOpacity": 0.7},
               "colorProp": "state_name",
               "valueMap": by_state}
    options = dict(style=dict(weight=1, color="#fff", fillOpacity=0.7))
    return hideout, options


@callback(
    Output("layer-raisg", "data"),
    Input("toggle-raisg", "value"),
)
def toggle_raisg(value):
    if "show" in (value or []):
        return RAISG_GEO
    return {"type": "FeatureCollection", "features": []}
```

**Step 4: Verify map renders**

Run app — map should show Brazil centered with state boundaries. Toggle RAISG checkbox — orange overlay appears/disappears.

**Step 5: Commit**

```bash
git add webapp/app.py
git commit -m "feat(map): Dash-Leaflet choropleth + RAISG territory toggle"
```

---

## Task 10: Simulation Section

**Files:**
- Modify: `webapp/simulation.py`
- Modify: `webapp/app.py`

**Step 1: Write test for simulation.py**

Add to `webapp/test_data_loader.py`:
```python
def test_projection_trend():
    import pandas as pd
    from simulation import project_deforestation
    # Synthetic input: 10 years of 1000 km²/year
    years = list(range(2015, 2025))
    areas = [1000.0] * 10
    result = project_deforestation(years, areas, rate_pct=0.0, horizon=2030)
    assert len(result) == 6  # 2025–2030
    assert abs(result[0] - 1000.0) < 1.0, "0% rate should keep same value"

def test_projection_decline():
    from simulation import project_deforestation
    years = list(range(2015, 2025))
    areas = [1000.0] * 10
    result = project_deforestation(years, areas, rate_pct=-10.0, horizon=2027)
    assert result[0] < 1000.0
    assert result[1] < result[0], "Should decline each year"

if __name__ == "__main__":
    test_load_returns_dataframe()
    test_projection_trend()
    test_projection_decline()
    print("All tests passed")
```

**Step 2: Run tests — expect failure**

```bash
cd webapp && python test_data_loader.py
```
Expected: `NotImplementedError`

**Step 3: Implement simulation.py**

```python
"""
Simple linear deforestation projection.
No external dependencies beyond numpy.
"""
import numpy as np


def project_deforestation(
    years: list[int],
    area_km2: list[float],
    rate_pct: float,
    horizon: int,
) -> list[float]:
    """
    Project annual deforestation forward from the last historical value.

    Args:
        years:     Historical years (e.g. [2000, 2001, ..., 2024])
        area_km2:  Annual deforestation matching years
        rate_pct:  Annual change rate in percent (e.g. -10.0 for -10%/year)
        horizon:   Last projection year (e.g. 2050)

    Returns:
        List of projected km² values for years (last_year+1) to horizon.
        Values are clamped to >= 0.
    """
    if not years or not area_km2:
        return []

    last_year = max(years)
    # Use mean of last 5 years as baseline (more stable than single year)
    recent = [a for y, a in zip(years, area_km2) if y >= last_year - 4]
    baseline = float(np.mean(recent)) if recent else float(area_km2[-1])

    multiplier = 1.0 + rate_pct / 100.0
    projection = []
    value = baseline
    for _ in range(horizon - last_year):
        value = max(0.0, value * multiplier)
        projection.append(round(value, 2))

    return projection


def cumulative_projection(projection: list[float]) -> list[float]:
    """Running cumulative sum of projected values."""
    total = 0.0
    result = []
    for v in projection:
        total += v
        result.append(round(total, 2))
    return result
```

**Step 4: Run tests — expect pass**

```bash
cd webapp && python test_data_loader.py
```
Expected: `All tests passed`

**Step 5: Add simulation layout to app.py**

Replace `html.Div(id="simulation-section")` with:

```python
    html.Div([
        html.H2("Simulation & Hochrechnung"),
        html.Div([
            html.Div([
                html.Label("Jährliche Änderungsrate"),
                dcc.Slider(
                    id="sim-rate", min=-15, max=15, step=0.5, value=-2,
                    marks={-15: "-15%", -10: "-10%", -5: "-5%",
                           0: "0%", 5: "+5%", 10: "+10%", 15: "+15%"},
                    tooltip={"placement": "bottom"},
                ),
            ], className="sim-slider"),
            html.Div([
                html.Label("Zeithorizont"),
                dcc.Slider(
                    id="sim-horizon", min=2030, max=2075, step=5, value=2050,
                    marks={y: str(y) for y in range(2030, 2076, 5)},
                    tooltip={"placement": "bottom"},
                ),
            ], className="sim-slider"),
        ], className="sim-controls"),

        html.Div([
            html.Button("Trend (letzte 5 J.)", id="preset-trend",   n_clicks=0),
            html.Button("Paris-kompatibel",   id="preset-paris",   n_clicks=0),
            html.Button("Null 2030",          id="preset-zero",    n_clicks=0),
        ], className="sim-presets"),

        html.Div(id="sim-result-text", className="sim-result"),
        dcc.Graph(id="chart-simulation", config={"displayModeBar": False}),
    ], className="simulation-section"),
```

**Step 6: Add simulation callbacks**

```python
@callback(
    Output("sim-rate", "value"),
    Input("preset-trend", "n_clicks"),
    Input("preset-paris", "n_clicks"),
    Input("preset-zero",  "n_clicks"),
    prevent_initial_call=True,
)
def apply_preset(trend_clicks, paris_clicks, zero_clicks):
    from dash import ctx
    triggered = ctx.triggered_id
    if triggered == "preset-paris":
        return -10.0
    if triggered == "preset-zero":
        return -30.0   # ~zero by 2030 from 2024 baseline
    # Trend: calculate actual trend from last 5 years
    ts = df.groupby("year")["area_km2"].sum().sort_index()
    if len(ts) >= 5:
        recent = ts.iloc[-5:].values
        rates = [(recent[i+1] - recent[i]) / recent[i] * 100
                 for i in range(len(recent)-1) if recent[i] > 0]
        return round(float(np.mean(rates)), 1) if rates else 0.0
    return 0.0


@callback(
    Output("chart-simulation", "figure"),
    Output("sim-result-text", "children"),
    Input("filter-biome", "value"),
    Input("filter-state", "value"),
    Input("sim-rate",    "value"),
    Input("sim-horizon", "value"),
)
def update_simulation(biome, state, rate_pct, horizon):
    from simulation import project_deforestation, cumulative_projection

    d = df.copy()
    if biome != "all":
        d = d[d["biome_name"] == biome]
    if state != "all":
        d = d[d["state_name"] == state]

    ts = d.groupby("year")["area_km2"].sum().sort_index()
    hist_years = ts.index.tolist()
    hist_vals  = ts.values.tolist()

    proj_vals  = project_deforestation(hist_years, hist_vals, rate_pct, horizon)
    proj_years = list(range(max(hist_years) + 1, horizon + 1))

    fig = go.Figure()
    # Historical
    fig.add_trace(go.Scatter(
        x=hist_years, y=hist_vals, name="Historisch",
        line=dict(color=GREEN_MED, width=2),
        hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
    ))
    # Projection
    if proj_vals:
        fig.add_trace(go.Scatter(
            x=proj_years, y=proj_vals, name="Projektion",
            line=dict(color=RED_MED, width=2, dash="dash"),
            hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
        ))
        # Vertical line at today
        fig.add_vline(
            x=max(hist_years), line_dash="dot", line_color="#999", line_width=1
        )

    fig.update_layout(**CHART_LAYOUT, showlegend=True, yaxis_title="km²/Jahr",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))

    # Result text
    if proj_vals:
        total_proj = sum(proj_vals)
        total_hist = sum(hist_vals)
        total_all  = total_hist + total_proj
        text = (
            f"Bei {rate_pct:+.1f}%/Jahr: Verlust bis {horizon} = "
            f"{total_proj:,.0f} km² (Projektion) · "
            f"Gesamtverlust seit 2000 = {total_all:,.0f} km² "
            f"(≈ {total_all / 357_114:.1f}× Deutschland)"
        )
    else:
        text = "Keine Projektion verfügbar."

    return fig, text
```

**Step 7: Run full test suite**

```bash
cd webapp && python test_data_loader.py
```
Expected: `All tests passed`

Run app — simulation chart renders, sliders + preset buttons work, result text updates.

**Step 8: Commit**

```bash
git add webapp/simulation.py webapp/app.py webapp/test_data_loader.py
git commit -m "feat(simulation): projection sliders, preset buttons, result text"
```

---

## Task 11: Docker Build & Deploy to rainforest.butscher.cloud

**Files:**
- Verify: `webapp/Dockerfile`
- Verify: `webapp/docker-compose.yml`
- Create: `webapp/.env` on VPS (not committed)

**Step 1: Build Docker image locally**

```bash
cd webapp
docker build -t rainforest-dashboard:latest .
```
Expected: Build succeeds, no errors.

**Step 2: Test container locally**

```bash
docker run --rm -p 8050:8050 \
  -e SUPABASE_URL=https://supabase.butscher.cloud \
  -e SUPABASE_KEY=your_anon_key \
  rainforest-dashboard:latest
```
Open `http://localhost:8050` — full dashboard should load with real data.

**Step 3: Push to Docker Hub (optional) or deploy directly**

Option A — copy to VPS via scp:
```bash
docker save rainforest-dashboard:latest | gzip > rainforest.tar.gz
scp rainforest.tar.gz user@vps:/opt/rainforest/
ssh user@vps "cd /opt/rainforest && docker load < rainforest.tar.gz"
```

Option B — push to Docker Hub:
```bash
docker tag rainforest-dashboard:latest swrobutsdocker/rainforest:latest
docker push swrobutsdocker/rainforest:latest
# Then on VPS: docker pull swrobutsdocker/rainforest:latest
```

**Step 4: Create .env on VPS**

On the VPS in `/opt/rainforest/`:
```bash
echo "SUPABASE_URL=https://supabase.butscher.cloud" > .env
echo "SUPABASE_KEY=your_anon_key" >> .env
```

**Step 5: Start with docker compose on VPS**

```bash
cd /opt/rainforest
docker compose up -d
```

**Step 6: Verify at rainforest.butscher.cloud**

Open `https://rainforest.butscher.cloud` — full dashboard with HTTPS via Traefik.

**Step 7: Final commit**

```bash
git add webapp/
git commit -m "feat(deploy): Docker + docker-compose for rainforest.butscher.cloud"
git push
```

---

## Summary of files created

```
UC4_Interaktive_Datenvisualisierung/
  db/
    rainforest_schema.sql
  deepnote/
    01_data_acquisition.ipynb
    02_geodata_prep.ipynb
  webapp/
    app.py
    data_loader.py
    simulation.py
    test_data_loader.py
    requirements.txt
    Dockerfile
    docker-compose.yml
    .env.example
    assets/
      style.css
      prodes_states.geojson
      raisg_territories.geojson
  docs/plans/
    2026-02-25-rainforest-dashboard-design.md
    2026-02-26-rainforest-dashboard-plan.md
```
