# Happiness Dashboard

Interaktives Dashboard auf Basis des *World Happiness Report* (2011–2025).
Architektur: PostgreSQL/Supabase + PostgREST + React/Vite/Recharts.
Datenmodell: **OBT** (one-big-table), bewusst gegen ein Sternschema entschieden
— Begründung im vorgelagerten Architektur-Vorschlag.

Dieses Projekt ist aus einem **Pre-Mortem** heraus gebaut: erst die wahrscheinlichen
Scheiternsgründe gesammelt, dann gezielt entkräftet. Die Gegenmaßnahmen sind
direkt im Code verankert, nicht nur im Kopf des Entwicklers.

---

## Pre-Mortem → Gegenmaßnahmen-Matrix

| # | Failure-Mode | Gegenmaßnahme | Wo im Code |
|---|---|---|---|
| F1 | Schema-Drift beim Jahresupdate | Spalten-Vertrag als Code, Pre-Flight-Check stoppt Pipeline | `scripts/validate_schema.py` (`EXPECTED_COLUMNS`) |
| F2 | NULL-Asymmetrie der Faktorspalten (2011–2018 leer) | Flag `has_factor_decomposition` in SSOT-View; Frontend degradiert gracefully | `db/04_views.sql` → `v_happiness`; `frontend/README.md` |
| F3 | Swaziland↔Eswatini-Rename | Beide Namen → ISO3 `SWZ` über Alias-Tabelle | `scripts/generate_country_seed.py` (`MANUAL`); `db/02_seed_countries.sql` |
| F4 | Nicht-ISO-Anzeigenamen (Korea, Hong Kong, Palestine, Taiwan) | Identität hängt an ISO3, nicht am Anzeigenamen | `db/01_schema.sql` → `country.iso3` als PK |
| F5 | Unicode-Apostroph in "Côte d'Ivoire" (`U+2019`) | Beide Schreibweisen als Aliase explizit gemappt | `scripts/generate_country_seed.py` (`MANUAL`) |
| F6 | Fehlendes Jahr 2013 | Wird *nicht* interpoliert; Charts setzen `connectNulls={false}` | `db/04_views.sql` → `v_country_year_grid`; `frontend/README.md` |
| F7 | Land-Zeitreihen-Lücken (Haiti, Belarus, Burundi, …) | LEFT-JOIN-Grid mit explizitem `is_gap`-Flag; `v_data_quality` listet Betroffene | `db/04_views.sql` → `v_country_year_grid`, `v_yoy` |
| F8 | Secrets im Git + fehlende RLS | `.env`/`.gitignore`; RLS revoked default, GRANT nur auf Views; service-role nie im Frontend | `.gitignore`, `.env.example`, `db/05_rls.sql` |
| F9 | Frontend-State-Spaghetti | URL-as-State für Permalink-würdiges, TanStack Query für Server-State | `frontend/README.md` (`useDashboardState`) |
| F10 | Logik-Verdoppelung (DB *und* Frontend rechnen) | Ranking/YoY ausschließlich in Views; Frontend ruft View, sortiert nicht selbst | `db/04_views.sql`; `frontend/README.md` (API-Layer-Regel) |
| F11 | Tabs-Wildwuchs / kein Story-Anker | Max. 4 Tabs, jeder mit analytischem Titel im Hichert-Stil | `frontend/README.md` |
| F12 | Refresh-Pfad undokumentiert | Versionsgesteuertes Runbook (dieses Dokument) + idempotenter SQL-Block | unten Abschnitt **Jahres-Refresh** |

---

## Projekt-Layout

```
happiness-dashboard/
├── README.md                       ← dieses Dokument
├── .env.example                    ← Vorlage, niemals echte Keys
├── .gitignore                      ← Secrets-Schutz
├── data/
│   └── world_happiness_data_2011_2025.csv
├── db/
│   ├── 01_schema.sql               ← Tabellen + Constraints
│   ├── 02_seed_countries.sql       ← ISO-Mapping (auto-generiert)
│   ├── 03_ingest.sql               ← Idempotenter Upsert
│   ├── 04_views.sql                ← API-Vertrag (SSOT + abgeleitete Views)
│   └── 05_rls.sql                  ← Read-only RLS für anon
├── scripts/
│   ├── generate_country_seed.py    ← regeneriert 02_seed_countries.sql
│   └── validate_schema.py          ← Vertragsprüfer vor jedem Refresh
└── frontend/
    └── README.md                   ← Konventionen (State, API-Layer)
```

---

## Erstaufbau

```bash
# 1. Voraussetzungen
python3 -m pip install pandas pycountry
# Supabase-Projekt anlegen, SUPABASE_DB_URL in .env eintragen

# 2. Schema + Lookups laden
psql "$SUPABASE_DB_URL" -f db/01_schema.sql
python3 scripts/generate_country_seed.py
psql "$SUPABASE_DB_URL" -f db/02_seed_countries.sql

# 3. Rohimport (Bronze-Schicht)
psql "$SUPABASE_DB_URL" -c "\copy happiness_raw(year,rank,country_name,life_evaluation_3y,lower_whisker,upper_whisker,explained_log_gdp,explained_social_support,explained_healthy_life,explained_freedom,explained_generosity,explained_corruption,dystopia_residual,source_url) FROM 'data/world_happiness_data_2011_2025.csv' CSV HEADER ENCODING 'UTF8'"

# 4. Typisierter Upsert
psql "$SUPABASE_DB_URL" -f db/03_ingest.sql

# 5. Views + RLS
psql "$SUPABASE_DB_URL" -f db/04_views.sql
psql "$SUPABASE_DB_URL" -f db/05_rls.sql

# 6. Smoke-Test
psql "$SUPABASE_DB_URL" -c "SELECT * FROM v_data_quality;"
```

---

## Jahres-Refresh (Runbook, ~5 Minuten)

Wenn WHR 2026 erscheint:

```bash
# A. Neue Datei ablegen
cp ~/Downloads/world_happiness_data_2011_2026.csv data/

# B. Vertrag prüfen — STOPP, wenn Schema kippt
python3 scripts/validate_schema.py data/world_happiness_data_2011_2026.csv

# C. Falls neue Ländernamen auftauchen, Generator erweitern und re-seed
python3 scripts/generate_country_seed.py
psql "$SUPABASE_DB_URL" -f db/02_seed_countries.sql

# D. Roh laden + Upsert (idempotent — Re-Run ist safe)
psql "$SUPABASE_DB_URL" -c "TRUNCATE happiness_raw;"
psql "$SUPABASE_DB_URL" -c "\copy happiness_raw(...) FROM 'data/world_happiness_data_2011_2026.csv' CSV HEADER ENCODING 'UTF8'"
psql "$SUPABASE_DB_URL" -f db/03_ingest.sql

# E. Verifikation
psql "$SUPABASE_DB_URL" -c "SELECT * FROM v_data_quality WHERE year >= 2024;"
```

Wenn Schritt B knallt: das ist kein Bug, das ist das Frühwarnsystem.

---

## Was *nicht* in diesem Projekt steckt — bewusst weggelassen

- Kein dbt, kein Airflow, kein Dagster — für 2.116 Zeilen Append-Only-Daten unverhältnismäßig.
- Kein Sternschema — siehe vorgelagerte OBT-vs-Star-Bilanz.
- Keine materialisierten Views — Datensatz ist klein genug, dass Views in <10 ms zurückkommen. Bei Performance-Druck später nachrüstbar.
- Kein eigenes Backend (FastAPI o. ä.) — PostgREST + Views reichen für read-only-OLAP.

Triggerkriterien für jeden dieser Bausteine sind im Pre-Mortem-Vorgespräch dokumentiert.
