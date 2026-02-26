"""
Amazon Rainforest Deforestation Dashboard
Datenquelle: INPE/PRODES via TerraBrasilis
"""
import json
import os

import requests
import dash
import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, State, callback, clientside_callback, ctx, dcc, html

try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False
    _anthropic = None

from data_loader import (
    SUPABASE_KEY,
    get_classes,
    get_states,
    get_years,
    load_deforestation_data,
)
from simulation import cumulative_projection, project_deforestation

if not SUPABASE_KEY:
    raise EnvironmentError("SUPABASE_KEY environment variable is not set")

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
YEARS = get_years()
CLASSES = get_classes()
STATES = get_states()
LATEST = max(YEARS)


def _compute_year_notes(dataframe) -> dict:
    """Derive factual annotations from actual data values (no invented context)."""
    ts = dataframe.groupby("year")["area_km2"].sum().sort_index()
    notes: dict[int, str] = {}
    if ts.empty:
        return notes
    peak_yr = int(ts.idxmax())
    min_yr = int(ts.idxmin())
    notes[peak_yr] = "Höchster Messwert im Datensatz"
    if min_yr != peak_yr:
        notes[min_yr] = "Niedrigster Messwert im Datensatz"
    pct = ts.pct_change()
    if len(pct) > 1:
        drop_yr = int(pct.idxmin())
        if drop_yr not in notes:
            notes[drop_yr] = f"Stärkster Rückgang im Vorjahresvergleich ({pct.min():.0%})"
        rise_yr = int(pct.idxmax())
        if rise_yr not in notes:
            notes[rise_yr] = f"Stärkster Anstieg im Vorjahresvergleich (+{pct.max():.0%})"
    return notes

# ── GeoJSON assets ────────────────────────────────────────────────────────────
_assets = os.path.join(os.path.dirname(__file__), "assets")

# Amazon Legal states: 2-letter code → IBGE numeric geocode
_CODE_TO_IBGE = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15",
    "AP": "16", "TO": "17", "MA": "21", "MT": "51",
}


def _fetch_states_geojson():
    """Fetch Amazon state boundaries from IBGE malhas API (one request per state)."""
    features = []
    base = "https://servicodados.ibge.gov.br/api/v3/malhas/estados"
    for code, ibge in _CODE_TO_IBGE.items():
        try:
            resp = requests.get(
                f"{base}/{ibge}?formato=application/vnd.geo+json", timeout=20
            )
            resp.raise_for_status()
            geo = resp.json()
            for feat in geo.get("features", []):
                feat.setdefault("properties", {})["state_code"] = code
                features.append(feat)
        except Exception as exc:
            print(f"Warning: Could not fetch {code} ({ibge}) from IBGE: {exc}")
    print(f"✓ Loaded {len(features)} Amazon state boundaries from IBGE")
    return {"type": "FeatureCollection", "features": features}


with open(os.path.join(_assets, "prodes_states.geojson"), encoding="utf-8") as f:
    STATES_GEO = json.load(f)

# If local file is empty (not yet generated), fetch live from IBGE
if not STATES_GEO.get("features"):
    STATES_GEO = _fetch_states_geojson()

# ── State name mapping ────────────────────────────────────────────────────────
STATE_NAME_MAP = {
    "AC": "Acre",
    "AM": "Amazonas",
    "AP": "Amapá",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "PA": "Pará",
    "RO": "Rondônia",
    "RR": "Roraima",
    "TO": "Tocantins",
}


def state_display(code):
    return STATE_NAME_MAP.get(code, code)


# ── German state area comparison ──────────────────────────────────────────────
GERMAN_STATES_KM2 = {
    "Bayern": 70_541,
    "Niedersachsen": 47_618,
    "Baden-Württemberg": 35_748,
    "NRW": 34_098,
    "Brandenburg": 29_654,
    "M.-Vorpommern": 23_213,
    "Hessen": 21_115,
    "Sachsen-Anhalt": 20_452,
    "Rheinland-Pfalz": 19_854,
    "Sachsen": 18_416,
    "Thüringen": 16_202,
    "Schleswig-Holstein": 15_800,
    "Saarland": 2_569,
    "Berlin": 892,
    "Hamburg": 755,
    "Bremen": 419,
}


def german_comparison(val_km2, lang="en"):
    """Return '<val> · ≈ Saarland' or '≈ 2.3× Bayern' comparison."""
    if val_km2 <= 0:
        return ""
    closest = min(GERMAN_STATES_KM2, key=lambda k: abs(GERMAN_STATES_KM2[k] - val_km2))
    area = GERMAN_STATES_KM2[closest]
    ratio = val_km2 / area
    ratio_s = fmt_mult(ratio, lang)
    if 0.85 <= ratio <= 1.15:
        return f"≈ {closest}"
    return f"≈ {ratio_s} {closest}"


# ── Number formatting ─────────────────────────────────────────────────────────
def fmt(val, lang="en", suffix=" km²", dec=0):
    """Format number with language-aware thousand/decimal separators."""
    s = f"{val:,.{dec}f}"
    if lang == "de":
        s = s.replace(",", "THOU").replace(".", ",").replace("THOU", ".")
    return s + suffix


def fmt_pct(val, lang="en"):
    s = f"{abs(val):.1f}"
    if lang == "de":
        s = s.replace(".", ",")
    return s + "%"


def fmt_mult(val, lang="en"):
    s = f"{val:.1f}"
    if lang == "de":
        s = s.replace(".", ",")
    return s + "×"


# ── Color palette ─────────────────────────────────────────────────────────────
GREEN_DARK  = "#1a3a2a"
GREEN_MED   = "#2d6a4f"
GREEN_LIGHT = "#52b788"
RED_MED     = "#ae2012"
TEXT        = "#1a1a1a"

# Base RGB for interpolation
_C_GREEN = (82, 183, 136)   # #52B788 — muted forest green
_C_RED   = (204, 96, 96)    # #CC6060 — muted brick red


def val_color(val, vmin, vmax, alpha=0.82):
    """Interpolate from muted green → muted dark red by relative value."""
    ratio = max(0.0, min(1.0, (val - vmin) / (vmax - vmin) if vmax > vmin else 0.5))
    r = int(_C_GREEN[0] + (_C_RED[0] - _C_GREEN[0]) * ratio)
    g = int(_C_GREEN[1] + (_C_RED[1] - _C_GREEN[1]) * ratio)
    b = int(_C_GREEN[2] + (_C_RED[2] - _C_GREEN[2]) * ratio)
    return f"rgba({r},{g},{b},{alpha})"


CHART_LAYOUT = dict(
    paper_bgcolor="white",
    plot_bgcolor="white",
    font=dict(family="Inter", size=13, color=TEXT),
    margin=dict(l=52, r=20, t=12, b=44),
    showlegend=False,
)

# Donut palette: muted forest green (#52B788) at descending opacity
STATE_COLORS = [
    "rgba(82,183,136,0.55)",
    "rgba(82,183,136,0.44)",
    "rgba(82,183,136,0.35)",
    "rgba(82,183,136,0.27)",
    "rgba(82,183,136,0.21)",
    "rgba(82,183,136,0.16)",
    "rgba(82,183,136,0.12)",
    "rgba(82,183,136,0.09)",
    "rgba(82,183,136,0.07)",
]

MAP_COLORSCALE = [
    [0.0,  "#f0faf5"],   # near-white — no deforestation
    [0.30, "#52b788"],   # muted green
    [0.65, "#e09090"],   # soft pink-red
    [1.0,  "#cc6060"],   # brick red — high deforestation
]

# Amazon reference areas (km²) for dramatic loss visualization
AMAZON_FOREST_KM2    = 4_100_000   # approximate original Legal Amazon forest cover
AMAZON_LOSS_PREDATA  = 700_000    # approximate cumulative loss before data start (INPE)
GERMANY_AREA_KM2     = 357_114             # Germany total area for KPI comparison

# Hover annotations for notable deforestation years
# NOTE: these are computed at runtime from actual data — see update_charts()
YEAR_NOTES: dict[int, str] = _compute_year_notes(df)

FOOTBALL_FIELD_KM2 = 0.00714   # 105 m × 68 m (FIFA-Standard)

# ── Lesehilfe (reading guides) ────────────────────────────────────────────────
LESEHILFE_FALLBACK = {
    "expand-ts": """#### Was zeigt dieses Chart?
Die Zeitreihe zeigt die jährlich gemessene Entwaldungsfläche (km²) im brasilianischen Amazonas.
Datenquelle: INPE/PRODES (Programm zur Schätzung der Entwaldung in der brasilianischen Amazonasregion,
Satelliten-Monitoring seit 1988). Das PRODES-Messjahr läuft von August bis Juli des Folgejahres.

#### Kernbotschaft
Die Bolsonaro-Regierung (1. Jan. 2019 – 31. Dez. 2022) markierte die höchsten Entwaldungsraten seit 2006.
Mit dem Amtsantritt von Lula da Silva am 1. Jan. 2023 sank die gemessene Rate deutlich – ein klarer Beweis,
dass politischer Wille direkte Messwirkung hat.

#### Hintergrund
Ca. 91 % der Entwaldungsakte im brasilianischen Amazonas galten 2023/24 als illegal (Quelle: ICV-Studie, 2025).
Brasilien unterzeichnete am 2. Nov. 2021 (COP26, Glasgow) die Glasgow Leaders' Declaration on Forests,
die bis 2030 den Stopp illegaler Entwaldung vorsieht. Der Amazonas speichert ca. 123 Mrd. Tonnen Kohlenstoff
(über- und unterirdisch, Quelle: NOAA) und beherbergt ca. 10 % der globalen Artenvielfalt.""",

    "expand-map": """#### Was zeigt dieses Chart?
Die animierte Karte zeigt den kumulierten Waldverlust je Bundesstaat von 2010 bis zum gewählten Jahr.
Dunklere Rotfärbung = höherer Gesamtverlust. Jeder Animationsframe addiert ein weiteres Jahr.

#### Kernbotschaft
Pará und Mato Grosso dominieren als größte Verlierer – beide sind Agrarbusiness-Zentren (Soja, Viehzucht).
Der sogenannte „Arc of Deforestation" – ein Halbmond von Rondônia über Pará bis Mato Grosso – ist klar erkennbar.

#### Hintergrund
Neue Infrastrukturprojekte (z.B. BR-163, Ferrogrão) öffnen bisher unzugängliche Waldgebiete und treiben
die Entwaldungsfront voran. Rondônia hat relativ zur Gesamtfläche bereits über 30 % seines ursprünglichen
Waldes verloren – eines der am stärksten betroffenen Bundesstaaten.""",

    "expand-top": """#### Was zeigt dieses Chart?
Das horizontale Ranking zeigt die 5 Bundesstaaten mit der höchsten Entwaldung im ausgewählten Jahr.

#### Kernbotschaft
Pará und Mato Grosso führen mit großem Abstand, da sie die größten amazoni­schen Bundesstaaten sind
und gleichzeitig intensive Landwirtschaft betreiben. Die jährlichen Verschiebungen im Ranking spiegeln
lokale Faktoren wie Niederschlag, Polizeipräsenz und Rohstoffpreise wider.

#### Hintergrund
Über 90 % der Entwaldung in Brasilien gilt als illegal – entlang von Straßen und Flüssen, oft durch organisierte
Landnahme („grilagem"). Die Entwaldungshotspots korrelieren stark mit globalen Sojaexporten und der
Rindfleischproduktion. Gezielter Druck auf wenige Bundesstaaten hätte daher große Hebelwirkung.""",

    "expand-donut": """#### Was zeigt dieses Chart?
Das Kreisdiagramm zeigt die prozentuale Verteilung der Entwaldung auf die Bundesstaaten für das gewählte Jahr.
Die Zahl in der Mitte gibt die Gesamtfläche des Jahres an.

#### Kernbotschaft
Pará und Mato Grosso machen regelmäßig über 50 % der Jahresentwaldung aus. Diese Konzentration ermöglicht
gezielte Maßnahmen mit maximaler Wirkung.

#### Hintergrund
Das PRODES-Monitoring (INPE) basiert auf Landsat/Sentinel-Satellitendaten (30 m Auflösung) und erfasst
Kahlschläge ≥ 6,25 ha. Kleinere Degradierungen durch selektiven Holzeinschlag oder Feuer werden separat
durch das DETER-System erfasst – die tatsächliche Walddegradierung übertrifft die PRODES-Zahlen um
den Faktor 2–3.""",

    "expand-cum": """#### Was zeigt dieses Chart?
Das gestapelte Säulendiagramm zeigt das verbleibende Waldkapital im Zeitverlauf. Grün = verbleibender Wald;
dunkelbraun = geschätzter historischer Verlust vor Datenbeginn; rot = gemessener Verlust im Datensatz.

#### Kernbotschaft
In Kombination mit dem historischen Vorverlust nähert sich der Gesamtschwund dem kritischen Schwellenwert.
Lovejoy & Nobre (Science Advances, 2018) warnen: Beim aktuellen Erwärmungsniveau droht ab ca. 20–25 %
Gesamtverlust ein irreversibler „Dieback"-Effekt.

#### Hintergrund
Beim Dieback verliert der Wald die Fähigkeit, eigene Niederschläge zu produzieren, trocknet aus und
verwandelt sich in Savanne – auch ohne weitere Abholzung. Carlos Nobre (INPE) schätzt, dass der Amazonas
bereits 15–17 % seiner Originalfläche verloren hat. Ein Durchbrechen der 20–25 %-Schwelle würde massive,
nicht umkehrbare CO₂-Freisetzung auslösen (Quelle: Lovejoy & Nobre, *Science Advances*, 2018,
DOI: 10.1126/sciadv.aat2340).""",

    "expand-sim": """#### Was zeigt dieses Chart?
Die Simulation projiziert die Entwaldungsrate auf Basis des letzten Messwerts mit der eingestellten
jährlichen Änderungsrate linear in die Zukunft.

#### Presets erklärt
**Paris-kompatibel (−10 %/Jahr):** Entspricht grob dem Tempo, das notwendig ist, um Brasiliens Zusage
aus der Glasgow Leaders' Declaration (COP26, 2. Nov. 2021) – Stopp illegaler Entwaldung bis 2030 –
annähernd zu erfüllen. Die Declaration wurde von über 140 Ländern unterzeichnet.
**Null 2030 (−30 %/Jahr):** Zeigt das rechnerisch notwendige Maximum für dieses Ziel.

#### Hintergrund
Lula da Silva (im Amt seit 1. Jan. 2023) hat Strafverfolgung und Monitoring reaktiviert.
Ca. 91 % der Entwaldung gilt als illegal (ICV, 2025) – wirksame Kontrolle hätte daher maximale Hebelwirkung.
Der Amazonas speichert ca. 123 Mrd. Tonnen Kohlenstoff (NOAA) – sein Schutz ist eine der
kosteneffizientesten Klimamaßnahmen weltweit.""",
}


def _gen_lesehilfe(key: str, context: str) -> str:
    """Generate Lesehilfe text via Claude API, fallback to static text."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not _HAS_ANTHROPIC:
        return LESEHILFE_FALLBACK.get(key, "Keine Lesehilfe verfügbar.")
    try:
        client = _anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": (
                    "Du bist Autor eines Amazon-Entwaldungs-Dashboards für einen Universitätskurs.\n"
                    f"Schreibe eine prägnante Lesehilfe auf Deutsch (~200 Wörter) für: **{context}**\n\n"
                    "Gliedere in Markdown:\n#### Was zeigt dieses Chart?\n(1-2 Sätze)\n\n"
                    "#### Kernbotschaft\n(2-3 Sätze)\n\n#### Hintergrund\n(3-4 Sätze, konkrete Fakten)\n\n"
                    "Sachlich, präzise, Bezug zu Amazonas/Klimapolitik/Brasilien."
                ),
            }],
        )
        return msg.content[0].text
    except Exception as exc:
        print(f"Warning: Lesehilfe API call failed for {key}: {exc}")
        return LESEHILFE_FALLBACK.get(key, "Keine Lesehilfe verfügbar.")


# ── Helpers ──────────────────────────────────────────────────────────────────
def filter_df(year, cls, state):
    d = df[df["year"] == year].copy()
    if cls != "all":
        d = d[d["class_name"] == cls]
    if state != "all":
        d = d[d["state_name"] == state]
    return d


def make_kpi_card(title, value_id, subtitle_id):
    return html.Div(
        [
            html.Div(title, className="kpi-title"),
            html.Div("—", id=value_id, className="kpi-value"),
            html.Div("", id=subtitle_id, className="kpi-subtitle"),
        ],
        className="kpi-card",
    )


# ── Layout ───────────────────────────────────────────────────────────────────
app.layout = html.Div(
    [
        # Hidden stores
        dcc.Store(id="modal-active-chart"),
        dcc.Store(id="map-ctrl-dummy"),
        # Header
        html.Header(
            [
                html.Div(
                    [
                        html.H1("Amazon Rainforest"),
                        html.P(f"Deforestation Monitor · INPE/PRODES {min(YEARS)}–{max(YEARS)}"),
                    ],
                    className="header-text",
                ),
                html.Div(
                    [
                        dcc.RadioItems(
                            id="lang-toggle",
                            options=[
                                {"label": "EN", "value": "en"},
                                {"label": "DE", "value": "de"},
                            ],
                            value="en",
                            inline=True,
                            className="lang-radio",
                        ),
                        html.Div(
                            [
                                html.Span("Datenquelle: "),
                                html.A(
                                    "TerraBrasilis / INPE",
                                    href="https://terrabrasilis.dpi.inpe.br",
                                    target="_blank",
                                ),
                            ],
                            className="header-source",
                        ),
                    ],
                    className="header-right",
                ),
            ],
            className="header",
        ),
        # Filter bar
        html.Div(
            [
                html.Div(
                    [
                        html.Label("Jahr"),
                        dcc.Dropdown(
                            id="filter-year",
                            options=[{"label": str(y), "value": y} for y in YEARS],
                            value=LATEST,
                            clearable=False,
                        ),
                    ],
                    className="filter-item",
                ),
                # Klasse-Filter ausgeblendet — nur eine Klasse (Desmatamento) vorhanden
                dcc.Dropdown(
                    id="filter-class",
                    options=[{"label": "Alle Klassen", "value": "all"}]
                    + [{"label": c, "value": c} for c in CLASSES],
                    value="all",
                    clearable=False,
                    style={"display": "none"},
                ),
                html.Div(
                    [
                        html.Label("Staat"),
                        dcc.Dropdown(
                            id="filter-state",
                            options=[{"label": "Alle Staaten", "value": "all"}]
                            + [{"label": STATE_NAME_MAP.get(s, s), "value": s} for s in STATES],
                            value="all",
                            clearable=False,
                        ),
                    ],
                    className="filter-item",
                ),
            ],
            className="filter-bar",
        ),
        # KPI cards
        html.Div(
            [
                # Card 1: dynamic title (year inserted by callback)
                html.Div(
                    [
                        html.Div("Gerodet (Jahr)", id="kpi-year-title", className="kpi-title"),
                        html.Div("—", id="kpi-year-val", className="kpi-value"),
                        html.Div("", id="kpi-year-sub", className="kpi-subtitle"),
                    ],
                    className="kpi-card",
                ),
                make_kpi_card(f"Kumuliert seit {min(YEARS)}", "kpi-total-val", "kpi-total-sub"),
                make_kpi_card("Staat mit höchster Rodung", "kpi-worst-val", "kpi-worst-sub"),
                make_kpi_card("Verlust-Tempo", "kpi-tempo-val", "kpi-tempo-sub"),
            ],
            className="kpi-row",
        ),
        # Charts grid
        html.Div(
            [
                # Zeitreihe
                html.Div(
                    [
                        html.Button("⤢", id="expand-ts", className="expand-btn", title="Vergrößern"),
                        html.H3("Jährliche Entwaldung"),
                        html.Div("Entwaldete Fläche km² pro Jahr · INPE PRODES", className="chart-sub"),
                        dcc.Graph(id="chart-timeseries", config={"displayModeBar": False}),
                    ],
                    className="chart-card",
                ),
                # Choropleth map (Plotly Mapbox)
                html.Div(
                    [
                        html.Button("⤢", id="expand-map", className="expand-btn", title="Vergrößern"),
                        html.H3("Entwaldung nach Bundesstaat"),
                        html.Div(
                            f"Kumulativer Waldverlust {min(YEARS)}–{max(YEARS)} · Farbe = Gesamtverlust bis zum jeweiligen Jahr",
                            className="chart-sub",
                        ),
                        html.Div(
                            [
                                html.Button("▶ Play", id="map-play-btn", className="map-ctrl-btn"),
                                html.Button("⏸ Pause", id="map-pause-btn", className="map-ctrl-btn"),
                            ],
                            className="map-controls",
                        ),
                        dcc.Graph(
                            id="chart-map",
                            config={"displayModeBar": False, "scrollZoom": True},
                        ),
                    ],
                    className="chart-card",
                ),
                # Top 5 Staaten
                html.Div(
                    [
                        html.Button("⤢", id="expand-top", className="expand-btn", title="Vergrößern"),
                        html.H3("Top 5 Staaten"),
                        html.Div(id="chart-topflop-sub", className="chart-sub"),
                        dcc.Graph(id="chart-topflop", config={"displayModeBar": False}),
                    ],
                    className="chart-card",
                ),
                # Staatsanteil Donut
                html.Div(
                    [
                        html.Button("⤢", id="expand-donut", className="expand-btn", title="Vergrößern"),
                        html.H3("Staatsanteil"),
                        html.Div(id="chart-donut-sub", className="chart-sub"),
                        dcc.Graph(id="chart-donut", config={"displayModeBar": False}),
                    ],
                    className="chart-card",
                ),
                # Kumulativer Area-Chart (full width)
                html.Div(
                    [
                        html.Button("⤢", id="expand-cum", className="expand-btn", title="Vergrößern"),
                        html.H3("Kumulativer Waldverlust"),
                        html.Div(
                            f"Verbleibend vs. vernichtet · Gesamtfläche Amazonas: 4,1 Mio. km²",
                            className="chart-sub",
                        ),
                        dcc.Graph(id="chart-cumulative", config={"displayModeBar": False}),
                    ],
                    className="chart-card full-width",
                ),
            ],
            className="charts-grid",
        ),
        # Simulation section
        html.Div(
            [
                html.H2("Simulation & Hochrechnung"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Label("Jährliche Änderungsrate"),
                                dcc.Slider(
                                    id="sim-rate",
                                    min=-15,
                                    max=15,
                                    step=0.5,
                                    value=-2,
                                    marks={
                                        -15: "-15%",
                                        -10: "-10%",
                                        -5: "-5%",
                                        0: "0%",
                                        5: "+5%",
                                        10: "+10%",
                                        15: "+15%",
                                    },
                                    tooltip={"placement": "bottom"},
                                ),
                            ],
                            className="sim-slider",
                        ),
                        html.Div(
                            [
                                html.Label("Zeithorizont"),
                                dcc.Slider(
                                    id="sim-horizon",
                                    min=2030,
                                    max=2075,
                                    step=5,
                                    value=2050,
                                    marks={y: str(y) for y in range(2030, 2076, 5)},
                                    tooltip={"placement": "bottom"},
                                ),
                            ],
                            className="sim-slider",
                        ),
                    ],
                    className="sim-controls",
                ),
                # Live projection KPIs — update as slider moves
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div("", id="sim-kpi-rate-label", className="sim-kpi-label"),
                                html.Div("—", id="sim-kpi-rate-val", className="sim-kpi-val"),
                            ],
                            className="sim-kpi-card",
                        ),
                        html.Div(
                            [
                                html.Div("Projektion kumuliert", className="sim-kpi-label"),
                                html.Div("—", id="sim-kpi-total-val", className="sim-kpi-val"),
                            ],
                            className="sim-kpi-card",
                        ),
                        html.Div(
                            [
                                html.Div("Wald verbleibend", className="sim-kpi-label"),
                                html.Div("—", id="sim-kpi-remaining-val", className="sim-kpi-val"),
                            ],
                            className="sim-kpi-card",
                        ),
                    ],
                    className="sim-kpi-row",
                ),
                html.Div(
                    [
                        html.Button("Trend (letzte 5 J.)", id="preset-trend", n_clicks=0),
                        html.Button("Paris-kompatibel", id="preset-paris", n_clicks=0),
                        html.Button("Null 2030", id="preset-zero", n_clicks=0),
                        html.Button("⤢ Vergrößern", id="expand-sim", className="expand-btn",
                                    style={"position": "static", "padding": "5px 12px",
                                           "width": "auto", "height": "auto"}),
                    ],
                    className="sim-presets",
                ),
                html.Div(
                    [
                        html.Strong("Pariser Klimaziele: "),
                        'Brasilien hat "null illegale Entwaldung bis 2030" zugesagt (Glasgow COP26, 2021). ',
                        html.Strong("Paris-kompatibel (−10 %/Jahr)"),
                        " entspricht dem notwendigen Mindesttempo für dieses Ziel. ",
                        html.Strong("Null 2030 (−30 %/Jahr)"),
                        " zeigt das rechnerische Maximum.",
                    ],
                    className="sim-context",
                ),
                html.Div(id="sim-result-text", className="sim-result"),
                dcc.Graph(id="chart-simulation", config={"displayModeBar": False}),
            ],
            className="simulation-section",
        ),
        # Footer
        html.Footer(
            "Daten: INPE PRODES via TerraBrasilis · IBGE (Staatsgrenzen) · "
            "Lovejoy & Nobre (Science Advances, 2018) · ICV (2025)",
            className="footer",
        ),
        # Modal overlay — expands any chart with Lesehilfe
        html.Div(
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("", id="modal-title"),
                            html.Button(
                                "✕ Schließen",
                                id="modal-close-btn",
                                className="modal-close-btn",
                                n_clicks=0,
                            ),
                        ],
                        className="modal-header",
                    ),
                    html.Div(
                        [
                            html.Div(
                                dcc.Graph(
                                    id="modal-graph",
                                    config={"displayModeBar": False},
                                    style={"height": "520px"},
                                ),
                                className="modal-chart",
                            ),
                            html.Div(
                                id="modal-lesehilfe-content",
                                className="modal-lesehilfe",
                            ),
                        ],
                        className="modal-body",
                    ),
                ],
                className="modal-box",
            ),
            id="modal-overlay",
            className="modal-overlay",
            style={"display": "none"},
        ),
    ],
    className="dashboard",
)


# ── Generate Lesehilfe texts at startup ───────────────────────────────────────
_LESEHILFE_CTX = {
    "expand-ts":    f"Jährliche Entwaldung — Zeitreihe km²/Jahr {min(YEARS)}–{max(YEARS)}, INPE PRODES",
    "expand-map":   f"Entwaldung nach Bundesstaat — Kumulierte animierte Choropleth-Karte {min(YEARS)}–{max(YEARS)}",
    "expand-top":   "Top 5 Bundesstaaten — Ranking nach jährlicher Entwaldungsfläche",
    "expand-donut": "Staatsanteil — Kreisdiagramm Jahresverteilung je Bundesstaat",
    "expand-cum":   f"Kumulativer Waldverlust — Gesamtfläche Amazon 4,1 Mio. km², {min(YEARS)}–{max(YEARS)}",
    "expand-sim":   "Simulation & Hochrechnung — Projektion mit Pariser Klimazielen (Glasgow-Deklaration 2021)",
}
print("Generating Lesehilfe texts...")
LESEHILFE: dict[str, str] = {k: _gen_lesehilfe(k, v) for k, v in _LESEHILFE_CTX.items()}
print("✓ Lesehilfe ready")


# ── Clientside callbacks ───────────────────────────────────────────────────────

# Map play / pause via HTML buttons (cleaner than Plotly updatemenus)
clientside_callback(
    """
    function(play_n, pause_n) {
        const ctx = window.dash_clientside.callback_context;
        if (!ctx.triggered.length) return window.dash_clientside.no_update;
        const btn_id = ctx.triggered[0].prop_id.split('.')[0];
        const el = document.getElementById('chart-map');
        if (!el) return window.dash_clientside.no_update;
        if (btn_id === 'map-play-btn') {
            el._mapPlaying = true;
            (function loop() {
                if (!el._mapPlaying) return;
                Plotly.animate(el, null, {
                    frame: {duration: 800, redraw: true},
                    transition: {duration: 200},
                    mode: 'afterall'
                }).then(function() {
                    if (el._mapPlaying) setTimeout(loop, 500);
                });
            })();
        } else {
            el._mapPlaying = false;
            try { Plotly.animate(el, [], {frame: {duration: 0}, mode: 'immediate'}); } catch(e) {}
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("map-ctrl-dummy", "data"),
    Input("map-play-btn", "n_clicks"),
    Input("map-pause-btn", "n_clicks"),
    prevent_initial_call=True,
)

# Modal: open on expand button click, close on close button
clientside_callback(
    """
    function(ts_n, map_n, top_n, donut_n, cum_n, sim_n, close_n,
             ts_fig, map_fig, top_fig, donut_fig, cum_fig, sim_fig) {
        const ctx = window.dash_clientside.callback_context;
        if (!ctx.triggered.length) return [window.dash_clientside.no_update,
                                           {display:'none'}, ''];
        const btn_id = ctx.triggered[0].prop_id.split('.')[0];
        if (btn_id === 'modal-close-btn') {
            return [window.dash_clientside.no_update, {display:'none'}, ''];
        }
        const lookup = {
            'expand-ts':    ts_fig,
            'expand-map':   map_fig,
            'expand-top':   top_fig,
            'expand-donut': donut_fig,
            'expand-cum':   cum_fig,
            'expand-sim':   sim_fig,
        };
        let fig = lookup[btn_id];
        if (!fig) return [window.dash_clientside.no_update, {display:'none'}, ''];
        // Keep sliders for map animation; only strip updatemenus (HTML buttons handle play/pause)
        if (btn_id === 'expand-map') {
            fig = JSON.parse(JSON.stringify(fig));
            if (fig.layout) { fig.layout.updatemenus = []; }
        }
        return [fig, {display:'flex'}, btn_id];
    }
    """,
    Output("modal-graph", "figure"),
    Output("modal-overlay", "style"),
    Output("modal-active-chart", "data"),
    Input("expand-ts", "n_clicks"),
    Input("expand-map", "n_clicks"),
    Input("expand-top", "n_clicks"),
    Input("expand-donut", "n_clicks"),
    Input("expand-cum", "n_clicks"),
    Input("expand-sim", "n_clicks"),
    Input("modal-close-btn", "n_clicks"),
    State("chart-timeseries", "figure"),
    State("chart-map", "figure"),
    State("chart-topflop", "figure"),
    State("chart-donut", "figure"),
    State("chart-cumulative", "figure"),
    State("chart-simulation", "figure"),
    prevent_initial_call=True,
)


@callback(
    Output("modal-lesehilfe-content", "children"),
    Output("modal-title", "children"),
    Input("modal-active-chart", "data"),
    prevent_initial_call=True,
)
def update_modal_lesehilfe(chart_id):
    if not chart_id:
        return "", ""
    titles = {
        "expand-ts":    "Jährliche Entwaldung",
        "expand-map":   "Entwaldung nach Bundesstaat",
        "expand-top":   "Top 5 Staaten",
        "expand-donut": "Staatsanteil",
        "expand-cum":   "Kumulativer Waldverlust",
        "expand-sim":   "Simulation & Hochrechnung",
    }
    text = LESEHILFE.get(chart_id, "")
    title = titles.get(chart_id, "")
    return dcc.Markdown(text), title


# ── KPI Callback ─────────────────────────────────────────────────────────────
@callback(
    Output("kpi-year-title", "children"),
    Output("kpi-year-val", "children"),
    Output("kpi-year-sub", "children"),
    Output("kpi-total-val", "children"),
    Output("kpi-total-sub", "children"),
    Output("kpi-worst-val", "children"),
    Output("kpi-worst-sub", "children"),
    Output("kpi-tempo-val", "children"),
    Output("kpi-tempo-sub", "children"),
    Input("filter-year", "value"),
    Input("filter-class", "value"),
    Input("filter-state", "value"),
    Input("lang-toggle", "value"),
)
def update_kpis(year, cls, state, lang):
    d = filter_df(year, cls, state)

    # Gerodet aktuelles Jahr
    kpi_year_title = f"Gerodet ({year})"
    area_year = d["area_km2"].sum()
    prev_d = filter_df(year - 1, cls, state) if year > min(YEARS) else None
    prev = prev_d["area_km2"].sum() if prev_d is not None else None
    if prev is not None and prev > 0:
        pct = (area_year - prev) / prev * 100
        is_good = pct < 0  # declining deforestation = good
        color = "#40916c" if is_good else "#ae2012"
        arrow = "▼" if is_good else "▲"
        delta = html.Span(
            [
                html.Span(f"{arrow} ", style={"color": color, "fontWeight": "700", "fontSize": "14px"}),
                f"{fmt_pct(pct, lang)} zum Vorjahr",
            ]
        )
    else:
        delta = ""
    kpi_year_val = fmt(area_year, lang)

    # Kumuliert
    d_all = df.copy()
    if cls != "all":
        d_all = d_all[d_all["class_name"] == cls]
    if state != "all":
        d_all = d_all[d_all["state_name"] == state]
    total = d_all[d_all["year"] <= year]["area_km2"].sum()
    kpi_total_val = fmt(total, lang)
    kpi_total_sub = f"≈ {fmt_mult(total / GERMANY_AREA_KM2, lang)} Deutschland" if total > 0 else ""

    # Staat mit höchster Rodung
    if state == "all" and len(d) > 0:
        by_st = d.groupby("state_name")["area_km2"].sum()
        worst = by_st.idxmax()
        worst_val = by_st.max()
        kpi_worst_val = state_display(worst)
        cmp = german_comparison(worst_val, lang)
        kpi_worst_sub = fmt(worst_val, lang) + (f" · {cmp}" if cmp else "")
    elif state != "all":
        kpi_worst_val = state_display(state)
        cmp = german_comparison(area_year, lang)
        kpi_worst_sub = fmt(area_year, lang) + (f" · {cmp}" if cmp else "")
    else:
        kpi_worst_val = "—"
        kpi_worst_sub = ""

    # Verlust-Tempo: football fields per minute at current year's rate
    if area_year > 0:
        fields_per_min = (area_year / 365.25 / 24 / 60) / FOOTBALL_FIELD_KM2
        kpi_tempo_val = f"~{fields_per_min:.1f}"
    else:
        kpi_tempo_val = "—"
    kpi_tempo_sub = "Fußballfelder / Minute · 105 × 68 m"

    return (kpi_year_title, kpi_year_val, delta, kpi_total_val, kpi_total_sub,
            kpi_worst_val, kpi_worst_sub, kpi_tempo_val, kpi_tempo_sub)


# ── Map Callback — animated Zeitraffer choropleth ─────────────────────────────
@callback(
    Output("chart-map", "figure"),
    Input("filter-class", "value"),
)
def update_map(cls):
    all_years = sorted(df["year"].unique())
    last_year = all_years[-1]
    codes = list(STATE_NAME_MAP.keys())

    # Pre-compute cumulative totals so zmax is the worst-case final value
    d_all = df if cls == "all" else df[df["class_name"] == cls]
    cum_by_state = d_all.groupby(["state_name", "year"])["area_km2"].sum().groupby("state_name").cumsum()
    zmax = float(cum_by_state.max())

    def make_trace(year):
        # Cumulative loss per state UP TO this year — colors only ever get darker
        d = d_all[d_all["year"] <= year]
        by_state = d.groupby("state_name")["area_km2"].sum()
        z_values = [float(by_state.get(c, 0)) for c in codes]
        annual = d_all[d_all["year"] == year].groupby("state_name")["area_km2"].sum()
        hover_texts = [
            f"<b>{STATE_NAME_MAP[c]}</b><br>"
            f"Kumulativ bis {year}: {by_state.get(c, 0):,.0f} km²<br>"
            f"Davon {year}: {annual.get(c, 0):,.0f} km²"
            for c in codes
        ]
        return go.Choroplethmapbox(
            geojson=STATES_GEO,
            locations=codes,
            z=z_values,
            featureidkey="properties.state_code",
            colorscale=MAP_COLORSCALE,
            zmin=0, zmax=zmax,
            colorbar=dict(
                title="km² kum.", thickness=10, len=0.55,
                tickformat=",.0f", titleside="right",
                titlefont=dict(size=11), tickfont=dict(size=11),
            ),
            hovertext=hover_texts,
            hoverinfo="text",
            marker_opacity=0.82,
            marker_line_width=1,
            marker_line_color="white",
        )

    def year_annotation(yr):
        """Large Gapminder-style year watermark drawn on the map."""
        return dict(
            text=f"<b>{yr}</b>",
            x=0.97, y=0.06,
            xref="paper", yref="paper",
            xanchor="right", yanchor="bottom",
            font=dict(size=64, color="rgba(26,42,26,0.18)", family="Inter"),
            showarrow=False,
        )

    # Each frame carries its own layout so the big year number updates
    frames = [
        go.Frame(
            data=[make_trace(yr)],
            name=str(yr),
            layout=go.Layout(annotations=[year_annotation(yr)]),
        )
        for yr in all_years
    ]

    fig = go.Figure(data=[make_trace(last_year)], frames=frames)
    fig.update_layout(
        annotations=[year_annotation(last_year)],
        sliders=[{
            "active": len(all_years) - 1,
            "steps": [
                {
                    "args": [[str(yr)], {"frame": {"duration": 800, "redraw": True}, "mode": "immediate"}],
                    "label": str(yr),
                    "method": "animate",
                }
                for yr in all_years
            ],
            "currentvalue": {"visible": False},
            "pad": {"b": 8, "t": 32},
            "font": {"family": "Inter", "size": 10, "color": "#999"},
            "len": 1.0, "x": 0.0,
            "bgcolor": "rgba(255,255,255,0)",
            "bordercolor": "#ddd",
        }],
        mapbox_style="open-street-map",
        mapbox_center={"lat": -5, "lon": -58},
        mapbox_zoom=3.2,
        paper_bgcolor="white",
        font=dict(family="Inter", size=13, color=TEXT),
        margin=dict(l=0, r=0, t=0, b=76),
        height=460,
    )
    return fig


# ── Charts Callback ───────────────────────────────────────────────────────────
@callback(
    Output("chart-timeseries", "figure"),
    Output("chart-topflop", "figure"),
    Output("chart-topflop-sub", "children"),
    Output("chart-donut", "figure"),
    Output("chart-donut-sub", "children"),
    Output("chart-cumulative", "figure"),
    Input("filter-year", "value"),
    Input("filter-class", "value"),
    Input("filter-state", "value"),
    Input("lang-toggle", "value"),
)
def update_charts(year, cls, state, lang):
    d_all = df.copy()
    if cls != "all":
        d_all = d_all[d_all["class_name"] == cls]
    if state != "all":
        d_all = d_all[d_all["state_name"] == state]

    d_year = filter_df(year, cls, state)

    # ── Zeitreihe — Säulendiagramm mit Datenlabel ─────────────────────────
    ts = d_all.groupby("year")["area_km2"].sum().reset_index()
    max_val = ts["area_km2"].max()
    # Muted green for all bars; peak gets brick red accent
    bar_colors = [
        "rgba(204,96,96,0.55)" if v == max_val else "rgba(82,183,136,0.45)"
        for v in ts["area_km2"]
    ]
    hover_texts = []
    for _, row in ts.iterrows():
        note = YEAR_NOTES.get(int(row["year"]), "")
        base = f"<b>{int(row['year'])}</b>  {row['area_km2']:,.0f} km²"
        hover_texts.append(base + (f"<br><i>{note}</i>" if note else ""))

    bar_text = [f"{int(v):,}" for v in ts["area_km2"]]
    fig_ts = go.Figure(
        go.Bar(
            x=ts["year"], y=ts["area_km2"],
            marker_color=bar_colors,
            text=bar_text,
            textposition="outside",
            textfont=dict(size=11, color="#444"),
            hovertext=hover_texts,
            hoverinfo="text",
            width=0.88,
        )
    )
    fig_ts.update_layout(
        **{**CHART_LAYOUT, "margin": dict(l=12, r=20, t=12, b=44)},
        xaxis_title="Jahr",
        xaxis=dict(tickfont=dict(size=12), dtick=1, tickangle=-45),
        yaxis=dict(visible=False, range=[0, max_val * 1.28]),
        bargap=0.10,
    )

    # ── Top 5 Staaten — wertbasierte Farbe, Datenlabel ────────────────────
    by_st = d_year.groupby("state_name")["area_km2"].sum().sort_values(ascending=False)
    top5_desc = by_st.head(5)
    top5 = top5_desc.sort_values(ascending=True)   # highest at top in horizontal bar
    top5_labels = [state_display(s) for s in top5.index]
    # Brick red for top-5; largest bar stronger accent
    top5_colors = [
        "rgba(204,96,96,0.55)" if v == top5.max() else "rgba(204,96,96,0.32)"
        for v in top5.values
    ]
    fig_top = go.Figure(
        go.Bar(
            y=top5_labels, x=top5.values,
            orientation="h",
            marker_color=top5_colors,
            text=[f"{int(v):,}" for v in top5.values],
            textposition="outside",
            textfont=dict(size=12),
            width=0.55,
            hovertemplate="%{y}: %{x:,.0f} km²<extra></extra>",
        )
    )
    fig_top.update_layout(
        **CHART_LAYOUT,
        xaxis=dict(visible=False),
        yaxis=dict(tickfont=dict(size=13)),
        xaxis_range=[0, top5.max() * 1.42],
        bargap=0.45,
    )
    topflop_sub = f"Meiste Entwaldung · {year}"

    # ── Staatsanteil Donut — sortiert, Jahreswert in Mitte ────────────────
    all_by_st = d_year.groupby("state_name")["area_km2"].sum().sort_values(ascending=False)
    donut_labels = [state_display(s) for s in all_by_st.index]
    total_year = all_by_st.sum()
    center_text = f"<b>{fmt(total_year, lang, suffix='')}</b><br>km²<br>{year}"
    fig_donut = go.Figure(
        go.Pie(
            labels=donut_labels,
            values=all_by_st.values,
            hole=0.5,
            marker_colors=STATE_COLORS[: len(all_by_st)],
            textposition="inside",
            textfont=dict(size=12),
            hovertemplate="%{label}: %{value:,.0f} km² (%{percent})<extra></extra>",
            direction="clockwise",
        )
    )
    fig_donut.update_layout(
        **{**CHART_LAYOUT, "showlegend": True, "margin": dict(l=8, r=100, t=8, b=8)},
        legend=dict(
            font=dict(size=13),
            x=1.02, y=0.5, xanchor="left",
            itemsizing="constant",
            bordercolor="#e0e0dc",
            borderwidth=1,
        ),
        annotations=[dict(
            text=center_text,
            x=0.5, y=0.5,
            font=dict(size=13, family="Inter", color=TEXT),
            showarrow=False,
            align="center",
        )],
    )
    donut_sub = f"Anteil je Staat · {year}"

    # ── Kumulativer Verlust — Vertikales Säulendiagramm (Zeit auf x-Achse) ─
    cum_loss_our = d_all.groupby("year")["area_km2"].sum().cumsum()
    total_loss = AMAZON_LOSS_PREDATA + cum_loss_our
    remaining = AMAZON_FOREST_KM2 - total_loss
    loss_pct = (total_loss / AMAZON_FOREST_KM2 * 100).round(1)

    fig_cum = go.Figure()
    fig_cum.add_trace(go.Bar(
        x=cum_loss_our.index,
        y=remaining.values,
        name="Verbleibend",
        marker=dict(color="rgba(82,183,136,0.45)", line=dict(width=0)),
        hovertemplate="<b>%{x}</b><br>Verbleibend: %{y:,.0f} km²<extra></extra>",
    ))
    fig_cum.add_trace(go.Bar(
        x=cum_loss_our.index,
        y=[AMAZON_LOSS_PREDATA] * len(cum_loss_our),
        name="Verlust vor 2010",
        marker=dict(color="rgba(140,20,20,0.88)", line=dict(width=0)),
        hovertemplate="<b>%{x}</b><br>Verlust vor 2010: ~700.000 km²<extra></extra>",
    ))
    fig_cum.add_trace(go.Bar(
        x=cum_loss_our.index,
        y=cum_loss_our.values,
        name="Verlust 2010–heute",
        marker=dict(color="rgba(204,96,96,0.45)", line=dict(width=0)),
        hovertemplate="<b>%{x}</b><br>Verlust 2010–%{x}: %{y:,.0f} km²<br>%{customdata:.1f}% vernichtet<extra></extra>",
        customdata=loss_pct.values,
    ))
    fig_cum.update_layout(
        **{**CHART_LAYOUT, "showlegend": True, "margin": dict(l=60, r=20, t=44, b=44)},
        barmode="stack",
        xaxis_title="Jahr",
        yaxis_title="km²",
        xaxis=dict(dtick=2, tickmode="linear", tickfont=dict(size=12)),
        yaxis=dict(tickformat=",.0f", tickfont=dict(size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=13)),
        annotations=[dict(
            x=0.5, y=1.10, xref="paper", yref="paper",
            text=f"Gesamtfläche Amazon: {AMAZON_FOREST_KM2 / 1e6:.1f} Mio. km² · "
                 f"Vernichtet gesamt: {loss_pct.iloc[-1]:.1f}%",
            showarrow=False,
            font=dict(size=11, color="#888"),
            align="center",
        )],
    )

    return fig_ts, fig_top, topflop_sub, fig_donut, donut_sub, fig_cum


# ── Simulation Callbacks ──────────────────────────────────────────────────────
@callback(
    Output("sim-rate", "value"),
    Input("preset-trend", "n_clicks"),
    Input("preset-paris", "n_clicks"),
    Input("preset-zero", "n_clicks"),
    prevent_initial_call=True,
)
def apply_preset(trend_clicks, paris_clicks, zero_clicks):
    triggered = ctx.triggered_id
    if triggered == "preset-paris":
        return -10.0
    if triggered == "preset-zero":
        return -30.0
    ts = df.groupby("year")["area_km2"].sum().sort_index()
    if len(ts) >= 5:
        recent = ts.iloc[-5:].values
        rates = [
            (recent[i + 1] - recent[i]) / recent[i] * 100
            for i in range(len(recent) - 1)
            if recent[i] > 0
        ]
        return round(float(np.mean(rates)), 1) if rates else 0.0
    return 0.0


@callback(
    Output("chart-simulation", "figure"),
    Output("sim-result-text", "children"),
    Output("sim-kpi-rate-val", "children"),
    Output("sim-kpi-total-val", "children"),
    Output("sim-kpi-remaining-val", "children"),
    Output("sim-kpi-rate-label", "children"),
    Input("filter-class", "value"),
    Input("filter-state", "value"),
    Input("sim-rate", "value"),
    Input("sim-horizon", "value"),
    Input("lang-toggle", "value"),
)
def update_simulation(cls, state, rate_pct, horizon, lang):
    d = df.copy()
    if cls != "all":
        d = d[d["class_name"] == cls]
    if state != "all":
        d = d[d["state_name"] == state]

    ts = d.groupby("year")["area_km2"].sum().sort_index()
    hist_years = ts.index.tolist()
    hist_vals = ts.values.tolist()

    proj_vals = project_deforestation(hist_years, hist_vals, rate_pct, horizon)
    proj_years = list(range(max(hist_years) + 1, horizon + 1))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=hist_years, y=hist_vals, name="Historisch",
            line=dict(color=GREEN_MED, width=2),
            hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
        )
    )
    if proj_vals:
        # Prepend last historical point to connect projection trace to history
        proj_years_conn = [hist_years[-1]] + proj_years
        proj_vals_conn = [hist_vals[-1]] + proj_vals
        fig.add_trace(
            go.Scatter(
                x=proj_years_conn, y=proj_vals_conn, name="Projektion",
                line=dict(color=RED_MED, width=2, dash="dash"),
                hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
            )
        )
        fig.add_vline(x=max(hist_years), line_dash="dot", line_color="#999", line_width=1)

    fig.update_layout(
        **{**CHART_LAYOUT, "showlegend": True},
        yaxis_title="km²/Jahr",
        xaxis=dict(tickfont=dict(size=12)),
        yaxis=dict(tickfont=dict(size=12), gridcolor="#eeeeea"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=13)),
        transition=dict(duration=600, easing="cubic-in-out"),
    )

    if proj_vals:
        total_proj = sum(proj_vals)
        total_hist = sum(hist_vals)
        total_all = total_hist + total_proj
        sign = "+" if rate_pct > 0 else "−"
        text = (
            f"Bei {sign}{fmt_pct(abs(rate_pct), lang)}/Jahr: Verlust bis {horizon} = "
            f"{fmt(total_proj, lang)} (Projektion) · "
            f"Gesamtverlust seit {min(hist_years)} = {fmt(total_all, lang)} "
            f"(≈ {fmt_mult(total_all / GERMANY_AREA_KM2, lang)} Deutschland)"
        )
        # Simulation KPI values
        kpi_rate = fmt(max(0.0, proj_vals[-1]), lang)
        kpi_total = fmt(total_proj, lang)
        # Remaining Amazon forest — always from full unfiltered data for ecological meaning
        full_ts = df.groupby("year")["area_km2"].sum().sort_index()
        full_proj = project_deforestation(
            full_ts.index.tolist(), full_ts.values.tolist(), rate_pct, horizon
        )
        remaining_km2 = (
            AMAZON_FOREST_KM2 - AMAZON_LOSS_PREDATA - float(full_ts.sum()) - sum(full_proj)
        )
        remaining_pct = max(0.0, remaining_km2 / AMAZON_FOREST_KM2 * 100)
        kpi_remaining = f"{remaining_pct:.1f} %"
    else:
        text = "Keine Projektion verfügbar."
        kpi_rate = "—"
        kpi_total = "—"
        kpi_remaining = "—"

    kpi_rate_label = f"Rate {horizon}"
    return fig, text, kpi_rate, kpi_total, kpi_remaining, kpi_rate_label


if __name__ == "__main__":
    app.run(debug=True, port=8050)
