"""
Amazon Rainforest Deforestation Dashboard
Datenquelle: INPE/PRODES via TerraBrasilis
"""
import json
import os

import pandas as pd
import requests
import dash
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
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
    load_socio_view,
    load_dim_state,
    load_dim_municipality,
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
    if lang in ("de", "pt"):
        s = s.replace(",", "THOU").replace(".", ",").replace("THOU", ".")
    return s + suffix


def fmt_pct(val, lang="en"):
    s = f"{abs(val):.1f}"
    if lang in ("de", "pt"):
        s = s.replace(".", ",")
    return s + "%"


def fmt_mult(val, lang="en"):
    s = f"{val:.1f}"
    if lang in ("de", "pt"):
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

# Categorical colors per state (consistent across all charts)
STATE_CAT_COLORS = {
    "PA": "#900000", "MT": "#D4883A", "AM": "#3A7CA5", "RO": "#E54142",
    "MA": "#6B8E3A", "AC": "#97BC62", "RR": "#1D5673", "TO": "#B8860B",
    "AP": "#C0C0C0",
}

# Donut palette: muted forest green (#52B788) at descending opacity
STATE_COLORS = [
    "#900000",   # Emilia — deepest dark red   (Pará, always #1)
    "#B60000",   # Mia    — dark red
    "#D20001",   # Emma   — medium-dark red
    "#E54142",   # Laura  — medium red
    "#F36162",   # Marie  — medium-light red
    "#FB7B7A",   # Lea    — warm light red
    "#FF9391",   # Anna   — light warm red
    "#FFA7A6",   # Sophia — pale warm red
    "#FFBBBE",   # Lena   — lightest (tiny slices only)
]

# Donut redesign: Top 3 → reds, rest → elegant greys with transparency
DONUT_COLORS = [
    "#900000",                    # #1 — deepest red
    "#D20001",                    # #2 — medium-dark red
    "#F36162",                    # #3 — medium-light red
    "rgba(100,100,100,0.78)",     # #4 — dark grey
    "rgba(140,140,140,0.68)",     # #5
    "rgba(170,170,170,0.58)",     # #6
    "rgba(195,195,195,0.48)",     # #7
    "rgba(215,215,215,0.38)",     # #8
    "rgba(228,228,228,0.28)",     # #9 — lightest grey
]

MAP_COLORSCALE = [
    [0.0,  "#fff0f0"],   # near-white — no/minimal deforestation
    [0.25, "#FFBBBE"],   # light red
    [0.50, "#F36162"],   # medium red
    [0.75, "#D20001"],   # strong red
    [1.0,  "#900000"],   # deepest — highest deforestation
]

# ── Colorblind-safe palette (Okabe-Ito) ──────────────────────────────────────
CB_STATE_COLORS = [
    "#0072B2",  # blue
    "#D55E00",  # vermilion
    "#009E73",  # bluish green
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#CC79A7",  # reddish purple
    "#F0E442",  # yellow
    "#888888",  # gray
    "#4B4B4B",  # dark gray
]
CB_MAP_COLORSCALE = [
    [0.0,  "#f0f8ff"],
    [0.33, "#56B4E9"],   # sky blue
    [0.67, "#0072B2"],   # blue
    [1.0,  "#003066"],   # very dark blue
]

# ── Value-proportional graded palettes (no pink) ─────────────────────────────
# Light → dark (index 0 = low value, index -1 = high value)
_RED_GRADED = ["#E54142", "#D20001", "#B60000", "#900000"]
_CB_GRADED  = ["#E69F00", "#D55E00", "#B84700", "#7B3000"]   # orange → dark vermilion

# Heatmap colorscales
HEATMAP_COLORSCALE = [
    [0.0,   "#FFCED1"],
    [0.25,  "#FFBBBE"],
    [0.50,  "#F36162"],
    [0.75,  "#D20001"],
    [1.0,   "#900000"],
]
CB_HEATMAP_COLORSCALE = [
    [0.0,   "#f0f8ff"],
    [0.33,  "#56B4E9"],
    [0.67,  "#0072B2"],
    [1.0,   "#003066"],
]

DIVERGING_COLORSCALE = [
    [0.0,  "#1B7837"], [0.35, "#A6DBA0"], [0.5, "#F7F7F7"],
    [0.65, "#F4A582"], [1.0,  "#B2182B"],
]

# Region colors for bubble chart (Okabe-Ito, inherently CB-safe)
REGION_COLORS = {
    "Norte":        "#0072B2",
    "Nordeste":     "#E69F00",
    "Centro-Oeste": "#009E73",
}


def _graded_color(val, vmin, vmax, cb=False):
    """Map a value to a color shade proportional to its position in [vmin, vmax]."""
    palette = _CB_GRADED if cb else _RED_GRADED
    if vmax <= vmin:
        return palette[-1]
    ratio = (val - vmin) / (vmax - vmin)
    idx = min(len(palette) - 1, int(ratio * len(palette)))
    return palette[idx]

# Amazon reference areas (km²) for dramatic loss visualization
AMAZON_FOREST_KM2    = 4_100_000   # approximate original Legal Amazon forest cover
AMAZON_LOSS_PREDATA  = 700_000    # approximate cumulative loss before data start (INPE)
GERMANY_AREA_KM2     = 357_114             # Germany total area for KPI comparison

# Hover annotations for notable deforestation years
# NOTE: these are computed at runtime from actual data — see update_charts()
YEAR_NOTES: dict[int, str] = _compute_year_notes(df)
df_socio = load_socio_view()
df_dim_state = load_dim_state()
df_municipality = load_dim_municipality()

FOOTBALL_FIELD_KM2 = 0.00714   # 105 m × 68 m (FIFA-Standard)
CO2_PER_KM2 = 72_000            # tCO₂e/km² · Berechnung: SEEG 2022 (837 Mio. tCO₂e) / INPE 2022 (11.568 km²)
                                # Quelle: https://seeg.eco.br · https://terrabrasilis.dpi.inpe.br

# ── Bilingual UI texts ────────────────────────────────────────────────────────
T: dict[str, dict] = {
    "en": {
        "label_year": "Year", "label_state": "Federal State (Estado)", "state_all": "All Federal States (Estados)",
        "kpi_total_title": f"Cumulative since {min(YEARS)}",
        "kpi_worst_title": "Federal state with most deforestation",
        "kpi_tempo_title": lambda year: f"Loss rate (annual avg. {year})",
        "kpi_tempo_sub": lambda year: f"football fields / min. · 105 × 68 m",
        "title_ts": "Annual Deforestation",
        "sub_ts": "Deforested area km²/year · INPE PRODES",
        "title_map": "Deforestation by Federal State",
        "sub_map": f"Cumulative forest loss {min(YEARS)}–{max(YEARS)} · Color = total loss up to the selected year",
        "title_top": "Top 5 Federal States",
        "top_prefix": "Most deforestation",
        "title_donut": "Federal state share",
        "donut_prefix": "Share by federal state",
        "title_cum": "Cumulative Forest Loss",
        "sub_cum": "Remaining vs. destroyed · Total Amazon area: 4.1M km² · Label = cumulative total loss in %",
        "cum_leg_remaining": "Remaining", "cum_leg_pre": "Loss before 2010",
        "cum_leg_post": "Loss 2010–present",
        "cum_axis_year": "Year",
        "cum_annotation": lambda pct, yr, co2: (
            f"Amazon total: {AMAZON_FOREST_KM2/1e6:.1f}M km² · Total destroyed: {pct:.1f}% · "
            f"CO₂ since {yr}: ~{co2:.1f}Bn t CO₂e"
        ),
        "title_sankey": "Deforestation Drivers & Global Markets",
        "sub_sankey_prefix": "Where does the forest go?",
        "title_sim": "Projection & Scenario Analysis",
        "label_rate": "Annual change rate",
        "label_horizon": "Time horizon",
        "btn_trend": "Trend (last 5y)", "btn_paris": "Paris-compatible",
        "btn_zero": "Zero 2030", "btn_expand": "⤢ Expand",
        "sim_kpi_total": "Projected cumulative",
        "sim_kpi_remaining": "Forest remaining",
        "sim_context": [
            html.Strong("Paris Climate Goals: "),
            'Brazil pledged "zero illegal deforestation by 2030" (Glasgow COP26, 2021). ',
            html.Strong("Paris-compatible (−10%/year)"),
            " is the minimum pace needed for this goal. ",
            html.Strong("Zero 2030 (−30%/year)"),
            " shows the mathematical maximum.",
        ],
        "sim_result": lambda sign, pct, hor, proj, hist_yr, total, mult: (
            f"At {sign}{pct}/year: loss to {hor} = {proj} (projection) · "
            f"Total loss since {hist_yr} = {total} (≈ {mult} Germany)"
        ),
        "sim_rate_label": lambda hor: f"Deforestation rate {hor} (km²/year)",
        "topflop_sub": lambda yr: f"Most deforestation · {yr}",
        "donut_sub": lambda yr: f"Share by federal state · {yr}",
        "kpi_year_title": lambda yr: f"Deforested ({yr})",
        "kpi_year_pct": lambda arrow, pct: f"{arrow} {pct} vs. prior year",
        "kpi_total_sub": lambda mult: f"≈ {mult} Germany",
        "kpi_worst_sub": lambda val, cmp: val + (f" · {cmp}" if cmp else ""),
        "header_title": "Amazon Rainforest | Brazil",
        "header_subtitle": f"Deforestation Monitor · INPE/PRODES {min(YEARS)}–{max(YEARS)}",
        "header_source": "Data source:",
        "sankey_node_labels": [
            "Cattle Ranching", "Smallholders", "Soy Farming", "Logging", "Infrastructure",
            "Brazil Domestic", "China", "USA", "EU & Other Markets", "Timber Market",
        ],
        "sankey_link_labels": [
            "Beef · Domestic consumption", "Beef export", "Beef export", "Beef export",
            "Subsistence farming", "Soy export", "Soy export",
            "Timber products", "Infrastructure / Land opening",
        ],
        "sankey_co2_unit": "M t CO₂e",
        "map_cum_prefix": "Cumulative to",
        "map_year_prefix": "of which",
        "map_colorbar": "km² cum.",
        "sim_hist_name": "Historical",
        "sim_proj_name": "Projection",
        "sim_yaxis": "km²/year",
        "ts_co2_unit": "M t CO₂e",
        "cum_pct_destroyed": "% destroyed",
        "btn_colorblind": "◐ Colorblind",
        "title_heatmap": "Deforestation Heatmap",
        "sub_heatmap": "Annual deforestation by state · 2010–2024 · Color intensity = deforestation km²",
        "heatmap_abs": "km² (absolute)",
        "heatmap_norm": "per 1,000 km²",
        "heatmap_corr": "Correlation",
        "heatmap_change":   "Change vs. Prior Year",
        "title_treemap":    "Who Eats the Forest?",
        "sub_treemap":      "Hierarchy: Region → State → Municipality · Size = Amazônia Legal area · Color = deforestation intensity per 1,000 km²",
        "title_slope":      "Deforestation Rankings",
        "sub_slope":        "Rank 1 = highest deforestation area · Lines show ranking shifts over time",
        "title_scatter":    "Does Size Predict Deforestation?",
        "sub_scatter":      "State area vs. cumulative deforestation since 2010 · Bubble size = population",
        "title_marimekko":  "How Much Forest Has Each State Lost?",
        "sub_marimekko":    "Bar width = state area in Amazônia Legal · Red = cumulative deforestation since 2010",
        "heatmap_total_label": "Total",
        "bubble_xaxis": "State GDP (R$ millions)",
        "bubble_yaxis": "Deforestation per 100k inhabitants (km²)",
        "corr_panel": [
            html.H4("What is being shown?", style={"fontSize": "11px", "fontWeight": "600", "textTransform": "uppercase", "letterSpacing": "0.07em", "color": "#888", "marginBottom": "6px"}),
            html.P("Metric: Deforestation per 100,000 inhabitants (km²) · Data: 2010–2021", style={"fontWeight": "600", "marginBottom": "8px", "fontSize": "13px"}),
            html.P(
                "Normalising deforestation by population enables a fair comparison across states of very different sizes. "
                "States under structural land-use pressure show high values even with smaller absolute deforestation numbers. "
                "Comparing this metric against GDP per capita reveals a clear pattern: economically weaker states tend to have "
                "disproportionately high per-capita deforestation rates — a fingerprint of frontier land markets.",
                style={"marginBottom": "8px"},
            ),
            html.P("Sources: INPE PRODES · IBGE", style={"color": "#aaa", "fontSize": "11px", "marginBottom": "0"}),
        ],
        "small_gdp_label": "GDP (R$ Mio.)",
        "small_defor_label": "Deforestation (km²)",
        "small_total_title": "All States — Total Annual Deforestation",
    },
    "de": {
        "label_year": "Jahr", "label_state": "Bundesstaat (Estado)", "state_all": "Alle Bundesstaaten (Estados)",
        "kpi_total_title": f"Kumuliert seit {min(YEARS)}",
        "kpi_worst_title": "Bundesstaat mit höchster Rodung",
        "kpi_tempo_title": lambda year: f"Verlustrate (Jahresdurchschnitt {year})",
        "kpi_tempo_sub": lambda year: f"Fußballfelder / Min. · 105 × 68 m",
        "title_ts": "Jährliche Entwaldung",
        "sub_ts": "Entwaldete Fläche km² pro Jahr · INPE PRODES",
        "title_map": "Entwaldung nach Bundesstaat",
        "sub_map": f"Kumulativer Waldverlust {min(YEARS)}–{max(YEARS)} · Farbe = Gesamtverlust bis zum jeweiligen Jahr",
        "title_top": "Top 5 Bundesstaaten",
        "top_prefix": "Meiste Entwaldung",
        "title_donut": "Anteil je Bundesstaat",
        "donut_prefix": "Anteil je Bundesstaat",
        "title_cum": "Kumulativer Waldverlust",
        "sub_cum": "Verbleibend vs. vernichtet · Gesamtfläche Amazonas: 4,1 Mio. km² · Datenlabel = kumulierter Gesamtverlust in %",
        "cum_leg_remaining": "Verbleibend", "cum_leg_pre": "Verlust vor 2010",
        "cum_leg_post": "Verlust 2010–heute",
        "cum_axis_year": "Jahr",
        "cum_annotation": lambda pct, yr, co2: (
            f"Gesamtfläche Amazon: {AMAZON_FOREST_KM2/1e6:.1f} Mio. km² · "
            f"Vernichtet gesamt: {pct:.1f}% · CO₂ seit {yr}: ~{co2:.1f} Mrd. t CO₂e"
        ),
        "title_sankey": "Entwaldungs-Treiber & globale Absatzmärkte",
        "sub_sankey_prefix": "Wohin verschwindet der Wald?",
        "title_sim": "Projektion & Szenario-Analyse",
        "label_rate": "Jährliche Änderungsrate",
        "label_horizon": "Zeithorizont",
        "btn_trend": "Trend (letzte 5 J.)", "btn_paris": "Paris-kompatibel",
        "btn_zero": "Null 2030", "btn_expand": "⤢ Vergrößern",
        "sim_kpi_total": "Projektion kumuliert",
        "sim_kpi_remaining": "Wald verbleibend",
        "sim_context": [
            html.Strong("Pariser Klimaziele: "),
            'Brasilien hat "null illegale Entwaldung bis 2030" zugesagt (Glasgow COP26, 2021). ',
            html.Strong("Paris-kompatibel (−10 %/Jahr)"),
            " entspricht dem notwendigen Mindesttempo für dieses Ziel. ",
            html.Strong("Null 2030 (−30 %/Jahr)"),
            " zeigt das rechnerische Maximum.",
        ],
        "sim_result": lambda sign, pct, hor, proj, hist_yr, total, mult: (
            f"Bei {sign}{pct}/Jahr: Verlust bis {hor} = {proj} (Projektion) · "
            f"Gesamtverlust seit {hist_yr} = {total} (≈ {mult} Deutschland)"
        ),
        "sim_rate_label": lambda hor: f"Entwaldungsrate {hor} (km²/Jahr)",
        "topflop_sub": lambda yr: f"Meiste Entwaldung · {yr}",
        "donut_sub": lambda yr: f"Anteil je Bundesstaat · {yr}",
        "kpi_year_title": lambda yr: f"Gerodet ({yr})",
        "kpi_year_pct": lambda arrow, pct: f"{arrow} {pct} zum Vorjahr",
        "kpi_total_sub": lambda mult: f"≈ {mult} Deutschland",
        "kpi_worst_sub": lambda val, cmp: val + (f" · {cmp}" if cmp else ""),
        "header_title": "Abholzung des Amazonas-Regenwaldes | Brasilien",
        "header_subtitle": f"Entwaldungsmonitor · INPE/PRODES {min(YEARS)}–{max(YEARS)}",
        "header_source": "Datenquelle:",
        "sankey_node_labels": [
            "Rinderzucht", "Kleinbauern", "Sojaanbau", "Holzeinschlag", "Infrastruktur",
            "Brasilien Inland", "China", "USA", "EU & Andere Märkte", "Holzmarkt",
        ],
        "sankey_link_labels": [
            "Rindfleisch · Inlandsverbrauch", "Rindfleischexport", "Rindfleischexport", "Rindfleischexport",
            "Subsistenzlandwirtschaft", "Sojaexport", "Sojaexport",
            "Holzprodukte", "Infrastruktur / Erschließung",
        ],
        "sankey_co2_unit": "Mio. t CO₂e",
        "map_cum_prefix": "Kumulativ bis",
        "map_year_prefix": "davon",
        "map_colorbar": "km² kum.",
        "sim_hist_name": "Historisch",
        "sim_proj_name": "Projektion",
        "sim_yaxis": "km²/Jahr",
        "ts_co2_unit": "Mio. t CO₂e",
        "cum_pct_destroyed": "% vernichtet",
        "btn_colorblind": "◐ Farbenblind",
        "title_heatmap": "Entwaldungs-Heatmap",
        "sub_heatmap": "Jährliche Entwaldung je Staat · 2010–2024 · Farbintensität = Entwaldung km²",
        "heatmap_abs": "km² (absolut)",
        "heatmap_norm": "je 1.000 km²",
        "heatmap_corr": "Korrelation",
        "heatmap_change":   "Veränd. vs. Vorjahr",
        "title_treemap":    "Wer frisst den Wald?",
        "sub_treemap":      "Hierarchie: Region → Bundesstaat → Gemeinde · Größe = Amazônia-Legal-Fläche · Farbe = Entwaldungsintensität je 1.000 km²",
        "title_slope":      "Entwaldungs-Ranking",
        "sub_slope":        "Rang 1 = höchste Abholzung · Linien zeigen Rangverschiebungen über die Zeit",
        "title_scatter":    "Sagt die Größe die Abholzung voraus?",
        "sub_scatter":      "Staatsfläche vs. kumulative Abholzung seit 2010 · Blasengröße = Bevölkerung",
        "title_marimekko":  "Wie viel Wald hat jeder Staat verloren?",
        "sub_marimekko":    "Balkenbreite = Staatsfläche in Amazônia Legal · Rot = kumulative Abholzung seit 2010",
        "heatmap_total_label": "Gesamt",
        "bubble_xaxis": "Staats-PIB (Mio. R$)",
        "bubble_yaxis": "Entwaldung je 100.000 Einw. (km²)",
        "corr_panel": [
            html.H4("Was wird hier gezeigt?", style={"fontSize": "11px", "fontWeight": "600", "textTransform": "uppercase", "letterSpacing": "0.07em", "color": "#888", "marginBottom": "6px"}),
            html.P("Kennzahl: Entwaldung je 100.000 Einwohner (km²) · Daten: 2010–2021", style={"fontWeight": "600", "marginBottom": "8px", "fontSize": "13px"}),
            html.P(
                "Die Normierung auf die Bevölkerung ermöglicht einen fairen Vergleich zwischen Staaten sehr unterschiedlicher Größe. "
                "Staaten mit strukturellem Landnutzungsdruck weisen hohe Werte auf, selbst wenn die absolute Abholzungsfläche gering ist. "
                "Im Vergleich mit dem BIP je Einwohner zeigt sich ein klares Muster: Wirtschaftlich schwächere Staaten weisen tendenziell "
                "überproportional hohe bevölkerungsnormierte Abholzungsraten auf – ein Kennzeichen von Grenzlandmärkten.",
                style={"marginBottom": "8px"},
            ),
            html.P("Quellen: INPE PRODES · IBGE", style={"color": "#aaa", "fontSize": "11px", "marginBottom": "0"}),
        ],
        "small_gdp_label": "PIB (Mio. R$)",
        "small_defor_label": "Entwaldung (km²)",
        "small_total_title": "Alle Staaten — Gesamte Jahresentwaldung",
    },
    "pt": {
        "label_year": "Ano", "label_state": "Estado Federal (Estado)", "state_all": "Todos os Estados (Estados)",
        "kpi_total_title": f"Acumulado desde {min(YEARS)}",
        "kpi_worst_title": "Estado com maior desmatamento",
        "kpi_tempo_title": lambda year: f"Ritmo de perda (média anual {year})",
        "kpi_tempo_sub": lambda year: f"campos de futebol / min. · 105 × 68 m",
        "title_ts": "Desmatamento Anual",
        "sub_ts": "Área desmatada km²/ano · INPE PRODES",
        "title_map": "Desmatamento por Estado",
        "sub_map": f"Perda florestal acumulada {min(YEARS)}–{max(YEARS)} · Cor = perda total até o ano selecionado",
        "title_top": "Top 5 Estados",
        "top_prefix": "Maior desmatamento",
        "title_donut": "Participação por Estado",
        "donut_prefix": "Participação por Estado",
        "title_cum": "Perda Florestal Acumulada",
        "sub_cum": f"Remanescente vs. destruído · Área total Amazônia: 4,1 Mi km² · Rótulo = perda total acumulada em %",
        "cum_leg_remaining": "Remanescente", "cum_leg_pre": "Perda antes de 2010",
        "cum_leg_post": "Perda 2010–presente",
        "cum_axis_year": "Ano",
        "cum_annotation": lambda pct, yr, co2: (
            f"Área total Amazônia: {AMAZON_FOREST_KM2/1e6:.1f} Mi km² · "
            f"Destruído total: {pct:.1f}% · CO₂ desde {yr}: ~{co2:.1f} Bi t CO₂e"
        ),
        "title_sankey": "Causas do Desmatamento & Mercados Globais",
        "sub_sankey_prefix": "Para onde vai a floresta?",
        "title_sim": "Projeção & Análise de Cenários",
        "label_rate": "Taxa de variação anual",
        "label_horizon": "Horizonte temporal",
        "btn_trend": "Tendência (últ. 5 a.)", "btn_paris": "Compatível Paris",
        "btn_zero": "Zero 2030", "btn_expand": "⤢ Ampliar",
        "sim_kpi_total": "Projeção acumulada",
        "sim_kpi_remaining": "Floresta remanescente",
        "sim_context": [
            html.Strong("Metas Climáticas de Paris: "),
            'O Brasil comprometeu "zero desmatamento ilegal até 2030" (Glasgow COP26, 2021). ',
            html.Strong("Compatível com Paris (−10%/ano)"),
            " é o ritmo mínimo necessário para esta meta. ",
            html.Strong("Zero 2030 (−30%/ano)"),
            " mostra o máximo matemático.",
        ],
        "sim_result": lambda sign, pct, hor, proj, hist_yr, total, mult: (
            f"A {sign}{pct}/ano: perda até {hor} = {proj} (projeção) · "
            f"Perda total desde {hist_yr} = {total} (≈ {mult} Alemanha)"
        ),
        "sim_rate_label": lambda hor: f"Taxa de desmatamento {hor} (km²/ano)",
        "topflop_sub": lambda yr: f"Maior desmatamento · {yr}",
        "donut_sub": lambda yr: f"Participação por Estado · {yr}",
        "kpi_year_title": lambda yr: f"Desmatado ({yr})",
        "kpi_year_pct": lambda arrow, pct: f"{arrow} {pct} em relação ao ano anterior",
        "kpi_total_sub": lambda mult: f"≈ {mult} Alemanha",
        "kpi_worst_sub": lambda val, cmp: val + (f" · {cmp}" if cmp else ""),
        "header_title": "Floresta Amazônica | Brasil",
        "header_subtitle": f"Monitor de Desmatamento · INPE/PRODES {min(YEARS)}–{max(YEARS)}",
        "header_source": "Fonte de dados:",
        "sankey_node_labels": [
            "Pecuária", "Agricultores Familiares", "Soja", "Exploração Madeireira", "Infraestrutura",
            "Brasil Doméstico", "China", "EUA", "UE & Outros Mercados", "Mercado Madeireiro",
        ],
        "sankey_link_labels": [
            "Carne bovina · Consumo doméstico", "Exportação bovina", "Exportação bovina", "Exportação bovina",
            "Agricultura de subsistência", "Exportação de soja", "Exportação de soja",
            "Produtos madeireiros", "Infraestrutura / Abertura de terras",
        ],
        "sankey_co2_unit": "Mi t CO₂e",
        "map_cum_prefix": "Acumulado até",
        "map_year_prefix": "do qual",
        "map_colorbar": "km² acum.",
        "sim_hist_name": "Histórico",
        "sim_proj_name": "Projeção",
        "sim_yaxis": "km²/ano",
        "ts_co2_unit": "Mi t CO₂e",
        "cum_pct_destroyed": "% destruído",
        "btn_colorblind": "◐ Daltonismo",
        "title_heatmap": "Mapa de Calor do Desmatamento",
        "sub_heatmap": "Desmatamento anual por estado · 2010–2024 · Intensidade = desmatamento km²",
        "heatmap_abs": "km² (absoluto)",
        "heatmap_norm": "por 1.000 km²",
        "heatmap_corr": "Correlação",
        "heatmap_change":   "Variação vs. Ano Ant.",
        "title_treemap":    "Quem Come a Floresta?",
        "sub_treemap":      "Hierarquia: Região → Estado → Município · Tamanho = área na Amazônia Legal · Cor = intensidade por 1.000 km²",
        "title_slope":      "Ranking de Desmatamento",
        "sub_slope":        "Rank 1 = maior desmatamento · Linhas mostram mudanças de posição ao longo do tempo",
        "title_scatter":    "O Tamanho Prevê o Desmatamento?",
        "sub_scatter":      "Área estadual vs. desmatamento acumulado desde 2010 · Tamanho = população",
        "title_marimekko":  "Quanta Floresta Cada Estado Perdeu?",
        "sub_marimekko":    "Largura = área estadual na Amazônia Legal · Vermelho = desmatamento acumulado desde 2010",
        "heatmap_total_label": "Total",
        "bubble_xaxis": "PIB estadual (R$ milhões)",
        "bubble_yaxis": "Desmatamento por 100 mil hab. (km²)",
        "corr_panel": [
            html.H4("O que está sendo mostrado?", style={"fontSize": "11px", "fontWeight": "600", "textTransform": "uppercase", "letterSpacing": "0.07em", "color": "#888", "marginBottom": "6px"}),
            html.P("Métrica: Desmatamento por 100.000 habitantes (km²) · Dados: 2010–2021", style={"fontWeight": "600", "marginBottom": "8px", "fontSize": "13px"}),
            html.P(
                "Normalizar o desmatamento pela população permite uma comparação justa entre estados de tamanhos muito diferentes. "
                "Estados sob forte pressão de uso da terra apresentam valores altos mesmo com menor desmatamento absoluto. "
                "Ao comparar com o PIB per capita, emerge um padrão estrutural claro: estados economicamente mais frágeis tendem a "
                "apresentar taxas de desmatamento per capita desproporcionalmente altas — uma marca característica dos mercados de fronteira.",
                style={"marginBottom": "8px"},
            ),
            html.P("Fontes: INPE PRODES · IBGE", style={"color": "#aaa", "fontSize": "11px", "marginBottom": "0"}),
        ],
        "small_gdp_label": "PIB (R$ Mi.)",
        "small_defor_label": "Desmatamento (km²)",
        "small_total_title": "Todos os Estados — Desmatamento Total Anual",
    },
}


# ── Sankey: static deforestation-driver → market flow ────────────────────────
def _make_sankey_figure(lang="de"):
    """
    Sankey based on verified research data, scaled to 10,000 km² (representative year).
    Sources: MapBiomas Annual Report 2024 (drivers), ABIEC 2024 (beef exports),
             ABIOVE/ANEC 2023 via ComexStat MDIC (soy exports).
    Cattle export share: Brazil exports ~25% of beef production (ABIEC 2024).
    Soy China share: ~73% (ABIOVE 2023 / USDA FAS).
    """
    node_labels = T[lang]["sankey_node_labels"]
    node_colors = [
        "rgba(160,45,35,0.88)",   # cattle — dark red
        "rgba(195,125,45,0.88)",  # small farms — amber
        "rgba(200,158,55,0.88)",  # soy — golden
        "rgba(105,68,35,0.88)",   # logging — dark brown
        "rgba(100,100,115,0.88)", # infra — cool gray
        "rgba(45,106,79,0.82)",   # Brazil inland — brand forest green
        "rgba(40,75,165,0.82)",   # China — deep blue
        "rgba(25,105,195,0.82)",  # USA — blue
        "rgba(75,130,200,0.82)",  # EU/Others — lighter blue
        "rgba(80,55,32,0.82)",    # Holzmarkt — wood brown
    ]
    # (source_idx, target_idx, km2)  — labels from T dict
    lbl = T[lang]["sankey_link_labels"]
    links = [
        # Cattle (7,500 km²) → inland 75%, export 25% (China 46%, USA 8%, Others 46%)
        (0, 5, 5625, lbl[0]),
        (0, 6,  863, lbl[1]),
        (0, 7,  150, lbl[2]),
        (0, 8,  862, lbl[3]),
        # Small farms (1,700 km²) → subsistence / domestic
        (1, 5, 1700, lbl[4]),
        # Soy (500 km²) → China 73%, EU+Others 27%
        (2, 6,  365, lbl[5]),
        (2, 8,  135, lbl[6]),
        # Logging (200 km²) → wood products
        (3, 9,  200, lbl[7]),
        # Infrastructure (100 km²)
        (4, 8,  100, lbl[8]),
    ]
    link_colors = [
        "rgba(160,45,35,0.16)", "rgba(160,45,35,0.16)",
        "rgba(160,45,35,0.16)", "rgba(160,45,35,0.16)",
        "rgba(195,125,45,0.16)",
        "rgba(200,158,55,0.16)", "rgba(200,158,55,0.16)",
        "rgba(105,68,35,0.16)",
        "rgba(100,100,115,0.16)",
    ]
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=node_labels,
            color=node_colors,
            pad=18,
            thickness=22,
            line=dict(color="rgba(255,255,255,0.3)", width=0.5),
        ),
        link=dict(
            source=[l[0] for l in links],
            target=[l[1] for l in links],
            value=[l[2] for l in links],
            label=[l[3] for l in links],
            color=link_colors,
            customdata=[round(l[2] * CO2_PER_KM2 / 1e6, 1) for l in links],
            hovertemplate=(
                "<b>%{label}</b><br>"
                "%{value:,} km²<br>"
                f"≈ %{{customdata:.0f}} {T[lang]['sankey_co2_unit']}<extra></extra>"
            ),
        ),
    ))
    fig.update_layout(
        paper_bgcolor="white",
        font=dict(family="Inter", size=12, color=TEXT),
        margin=dict(l=8, r=8, t=8, b=8),
        height=380,
    )
    return fig


SANKEY_FIG = _make_sankey_figure("en")

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

    "expand-heatmap": """#### Was zeigt dieses Chart?
Die Heatmap zeigt die jährliche Entwaldung je Bundesstaat als Farbmatrix.
Jede Zelle steht für einen Staat in einem bestimmten Jahr; die Farbintensität codiert die entwaldete Fläche.

#### Kernbotschaft
Das Farbmuster macht Peaks und Hochdruckstaaten auf einen Blick sichtbar.
Die Bolsonaro-Jahre (2019–2022) zeigen klar höhere Intensitäten in fast allen Staaten.

#### Hintergrund
Die vier Anzeigemodi ermöglichen Vergleiche nach absoluten Werten (km²), relativer Intensität
(je 1.000 km²), Veränderung zum Vorjahr und Korrelation mit sozioökonomischen Indikatoren.
Quelle: INPE PRODES · IBGE.""",

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

    "expand-sankey": """#### Was zeigt dieses Diagramm?
Das Sankey-Diagramm visualisiert die Ursachen der Entwaldung (linke Seite) und zeigt, wohin
die erzeugten Produkte fließen (rechte Seite). Die Breite jedes Bandes ist proportional zur
entwaldeten Fläche – skaliert auf 10.000 km² als repräsentatives Jahr.

#### Kernbotschaft
Rinderzucht treibt rund 75 % der Entwaldung – und der Großteil des Rindfleischs wird im
brasilianischen Inland konsumiert. Sojaanbau (5 %) fließt überwiegend nach China.
Globale Konsummuster haben damit direkten Einfluss auf den amazonischen Waldverlust.

#### Quellen & Hintergrund
Treiberanteile: [MapBiomas Annual Report 2024](https://mapbiomas.org/en/annual-deforestation-report) ·
Rindfleischexporte: [ABIEC Beef Report 2024](https://www.abiec.com.br/en/beef-report/) ·
Sojaexporte: [ABIOVE/ANEC 2023](https://abiove.org.br) ·
CO₂-Koeffizient: [SEEG Brasil 2022](https://seeg.eco.br) (837 Mio. tCO₂e / 11.568 km² INPE = 72.300 tCO₂e/km²).
Infrastruktur (BR-163 u.a.) erschließt bisher unzugängliche Gebiete und ermöglicht nachfolgende
Rodungsschübe – ein Multiplikatoreffekt. Das Amazon Soy Moratorium (2006) hat soybedingte
Direktrodung eingedämmt; Entwaldung verlagerte sich auf Weideland, das Sojaanbau indirekt
ermöglicht (sog. „land displacement").""",

    "expand-sim": """#### Was zeigt dieses Chart?
Die Projektion extrapoliert die Entwaldungsrate auf Basis des letzten Messwerts mit der eingestellten
jährlichen Änderungsrate linear in die Zukunft (lineare Szenario-Projektion, kein Simulationsmodell).

#### Presets erklärt
**Paris-kompatibel (−10 %/Jahr):** Entspricht grob dem Tempo, das notwendig ist, um Brasiliens Zusage
aus der [Glasgow Leaders' Declaration](https://www.gov.uk/government/publications/glasgow-leaders-declaration-on-forests-and-land-use-2021-to-2030) (COP26, 2. Nov. 2021) – Stopp illegaler Entwaldung bis 2030 –
annähernd zu erfüllen. Über 140 Länder haben unterzeichnet.
**Null 2030 (−30 %/Jahr):** Zeigt das rechnerisch notwendige Maximum für dieses Ziel.

#### Hintergrund
Lula da Silva (im Amt seit 1. Jan. 2023) hat Strafverfolgung und Monitoring reaktiviert.
Ca. 91 % der Entwaldung gilt als illegal ([ICV, 2025](https://www.icv.org.br)) – wirksame Kontrolle hätte maximale Hebelwirkung.
Der Amazonas speichert ca. 123 Mrd. Tonnen Kohlenstoff ([NOAA](https://www.noaa.gov)) – sein Schutz ist eine der
kosteneffizientesten Klimamaßnahmen weltweit.""",

    "expand-treemap":   """#### Was zeigt dieses Diagramm?
Region → Bundesstaat → Gemeinde Hierarchie. Rechteckgröße = Amazônia-Legal-Fläche in km².
Farbe = Entwaldungsintensität je 1.000 km² (Staatsebene). Slider oder Play-Button für Animation.

#### Kernaussage
Pará (PA) und Amazonas (AM) dominieren flächenmäßig, aber die Farbe zeigt, welche Staaten
überproportional roden. Rondônia (RO) und Mato Grosso (MT) zeigen dauerhaft hohe Intensität
unabhängig vom Jahr — strukturelle Hotspots.

#### Hintergrund
Die Formen bleiben über alle Jahre konstant — nur die Farben ändern sich mit dem Rodungsdruck.
Das trennt strukturelle Geografie (wer das Land hält) von dynamischem Druck
(wer aktiv rodet). Quelle: IBGE · INPE PRODES.""",

    "expand-slope": """#### Was zeigt dieses Chart?
Das Slope-Diagramm zeigt die Rangverschiebungen der Bundesstaaten nach Abholzungsfläche über 2010–2024.
Rang 1 = höchste absolute Abholzung im Jahr. Kreuzende Linien zeigen Staaten, die relativ stärker oder schwächer werden.

#### Kernbotschaft
Staaten, die im Ranking aufsteigen, weisen wachsenden Druck auf; sinkende zeigen relative Verbesserung.
Rondônia und Mato Grosso halten dauerhaft hohe Positionen – strukturelle Hotspots unabhängig vom Jahr.

#### Hintergrund
Das Ranking eliminiert den Einfluss der absoluten Staatsgröße und zeigt, welche Staaten
ihr Rodungstempo beschleunigen oder verlangsamen. Quelle: INPE PRODES · IBGE.""",

    "expand-scatter": """#### Was zeigt dieses Chart?
Der Bubble-Chart vergleicht die Amazônia-Legal-Fläche jedes Staates mit der kumulierten Abholzung seit 2010.
Die Blasengröße entspricht der Bevölkerung; auf der x-Achse liegt das Staats-BIP.

#### Kernbotschaft
Punkte oberhalb der Trendlinie roden überproportional zu ihrer Fläche oder Wirtschaftsleistung.
Rondônia und Mato Grosso stechen als strukturelle Hochdruckstaaten hervor.

#### Hintergrund
Staaten mit höherem BIP je Einwohner zeigen tendenziell geringere relative Abholzung –
ein Hinweis, dass wirtschaftliche Entwicklung in Kombination mit Governance
die Walddegradierung reduzieren kann. Quelle: INPE PRODES · IBGE.""",

    "expand-marimekko": """#### Was zeigt dieses Chart?
Das Marimekko-Diagramm zeigt gleichzeitig die Amazônia-Legal-Fläche jedes Staates (Balkenbreite)
und den bereits abgeholzten Anteil (rote Höhe). Absolutgröße und relative Intensität lassen sich kombiniert ablesen.

#### Kernbotschaft
Staaten mit breiten Balken und großem roten Anteil kombinieren hohe Fläche und hohe Zerstörungsrate.
Kleine Prozentsätze können in großen Staaten wie Pará enorme absolute Verluste verbergen.

#### Hintergrund
Die Balkenbreite entspricht der Amazônia-Legal-Gesamtfläche; die rote Höhe zeigt den kumulierten
Abholzungsanteil seit 2010. Quelle: INPE PRODES · IBGE.""",
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


def make_kpi_card(title, value_id, subtitle_id, title_id=None):
    return html.Div(
        [
            html.Div(title, id=title_id, className="kpi-title"),
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
        dcc.Store(id="colorblind-mode", data=False),
        dcc.Store(id="heatmap-metric", data="abs"),
        dcc.Store(id="treemap-anim-dummy"),
        # Header
        html.Header(
            [
                html.Div(
                    [
                        html.H1("Amazon Rainforest", id="header-title"),
                        html.P(id="header-subtitle"),
                    ],
                    className="header-text",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                dcc.RadioItems(
                                    id="lang-toggle",
                                    options=[
                                        {"label": "EN", "value": "en"},
                                        {"label": "DE", "value": "de"},
                                        {"label": "PT", "value": "pt"},
                                    ],
                                    value="en",
                                    inline=True,
                                    className="lang-radio",
                                ),
                                html.Button(
                                    "◐ Colorblind",
                                    id="cb-toggle",
                                    className="cb-btn",
                                    n_clicks=0,
                                ),
                            ],
                            style={"display": "flex", "gap": "10px", "alignItems": "center"},
                        ),
                        html.Div(
                            [
                                html.Span(id="header-source"),
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
                        html.Label("Jahr", id="label-year"),
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
                        html.Label("Staat", id="label-state"),
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
                make_kpi_card(f"Kumuliert seit {min(YEARS)}", "kpi-total-val", "kpi-total-sub", "kpi-total-title"),
                make_kpi_card("Staat mit höchster Rodung", "kpi-worst-val", "kpi-worst-sub", "kpi-worst-title"),
                make_kpi_card("Verlust-Tempo", "kpi-tempo-val", "kpi-tempo-sub", "kpi-tempo-title"),
            ],
            className="kpi-row",
        ),
        # Charts grid
        html.Div(
            [
                # Zeitreihe — full width
                html.Div(
                    [
                        html.H3("Jährliche Entwaldung", id="title-ts"),
                        html.Div("Entwaldete Fläche km² pro Jahr · INPE PRODES", id="sub-ts", className="chart-sub"),
                        dcc.Graph(id="chart-timeseries", config={"displayModeBar": False}),
                        html.Div(id="lesehilfe-ts", className="chart-lesehilfe"),
                    ],
                    className="chart-card full-width",
                ),
                # Choropleth map
                html.Div(
                    [
                        html.Button("⤢", id="expand-map", className="expand-btn", title="Vergrößern"),
                        html.H3("Entwaldung nach Bundesstaat", id="title-map"),
                        html.Div(
                            f"Kumulativer Waldverlust {min(YEARS)}–{max(YEARS)} · Farbe = Gesamtverlust bis zum jeweiligen Jahr",
                            id="sub-map", className="chart-sub",
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
                # Staatsanteil Donut (right of map)
                html.Div(
                    [
                        html.Button("⤢", id="expand-donut", className="expand-btn", title="Vergrößern"),
                        html.H3("Staatsanteil", id="title-donut"),
                        html.Div(id="chart-donut-sub", className="chart-sub"),
                        dcc.Graph(id="chart-donut", config={"displayModeBar": False}),
                    ],
                    className="chart-card",
                ),
                # Heatmap — full width
                html.Div(
                    [
                        html.H3("Entwaldungs-Heatmap", id="title-heatmap"),
                        html.Div(id="sub-heatmap", className="chart-sub"),
                        html.Div(
                            [
                                html.Button("km² (absolut)", id="heatmap-abs-btn", n_clicks=0, className="heatmap-pill-active"),
                                html.Button("je 1.000 km²", id="heatmap-norm-btn", n_clicks=0),
                                html.Button("Korrelation", id="heatmap-corr-btn", n_clicks=0),
                                html.Button("Veränd. vs. Vorjahr", id="heatmap-change-btn", n_clicks=0),
                            ],
                            className="sim-presets",
                            style={"marginBottom": "8px", "marginTop": "4px"},
                        ),
                        dcc.Graph(id="chart-heatmap", config={"displayModeBar": False}),
                        html.Div(id="heatmap-corr-panel", style={"display": "none"}),
                        html.Div(id="lesehilfe-heatmap", className="chart-lesehilfe"),
                    ],
                    className="chart-card full-width",
                ),
                # Kumulativer Area-Chart (full width)
                html.Div(
                    [
                        html.H3("Kumulativer Waldverlust", id="title-cum"),
                        html.Div(
                            "Verbleibend vs. vernichtet · Gesamtfläche Amazonas: 4,1 Mio. km² · Datenlabel = kumulierter Gesamtverlust in %",
                            id="sub-cum", className="chart-sub",
                        ),
                        dcc.Graph(id="chart-cumulative", config={"displayModeBar": False}),
                        html.Div(id="lesehilfe-cum", className="chart-lesehilfe"),
                    ],
                    className="chart-card full-width",
                ),
                # Treemap: Who Eats the Forest?
                html.Div([
                    html.H3("Who Eats the Forest?", id="title-treemap"),
                    html.Div(id="sub-treemap", className="chart-sub"),
                    html.Div(
                        [
                            html.Button("▶ Play", id="treemap-play-btn", className="map-ctrl-btn"),
                            html.Button("⏸ Pause", id="treemap-pause-btn", className="map-ctrl-btn"),
                        ],
                        className="map-controls",
                    ),
                    dcc.Graph(id="chart-treemap", config={"displayModeBar": False}),
                    html.Div(id="lesehilfe-treemap", className="chart-lesehilfe"),
                ], className="chart-card full-width"),
                # Sankey: Deforestation drivers & global markets
                html.Div(
                    [
                        html.H3("Entwaldungs-Treiber & globale Absatzmärkte", id="title-sankey"),
                        html.Div(id="sub-sankey", className="chart-sub"),
                        dcc.Graph(
                            id="chart-sankey",
                            figure=SANKEY_FIG,
                            config={"displayModeBar": False},
                        ),
                        html.Div(id="lesehilfe-sankey", className="chart-lesehilfe"),
                    ],
                    className="chart-card full-width",
                ),
                # Slope Chart: Rankings
                html.Div([
                    html.H3("Deforestation Rankings", id="title-slope"),
                    html.Div(id="sub-slope", className="chart-sub"),
                    dcc.Graph(id="chart-slope", config={"displayModeBar": False}),
                    html.Div(id="lesehilfe-slope", className="chart-lesehilfe"),
                ], className="chart-card full-width"),
                # Scatter: Size vs Deforestation
                html.Div([
                    html.H3("Does Size Predict Deforestation?", id="title-scatter"),
                    html.Div(id="sub-scatter", className="chart-sub"),
                    dcc.Graph(id="chart-scatter", config={"displayModeBar": False}),
                    html.Div(id="lesehilfe-scatter", className="chart-lesehilfe"),
                ], className="chart-card full-width"),
            ],
            className="charts-grid",
        ),
        # Simulation section
        html.Div(
            [
                html.H2("Projektion & Szenario-Analyse", id="title-sim"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Label("Jährliche Änderungsrate", id="label-rate"),
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
                                html.Label("Zeithorizont", id="label-horizon"),
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
                            id="sim-kpi-rate-card",
                            className="sim-kpi-card",
                        ),
                        html.Div(
                            [
                                html.Div("Projektion kumuliert", id="sim-kpi-total-label", className="sim-kpi-label"),
                                html.Div("—", id="sim-kpi-total-val", className="sim-kpi-val"),
                            ],
                            id="sim-kpi-total-card",
                            className="sim-kpi-card",
                        ),
                        html.Div(
                            [
                                html.Div("Wald verbleibend", id="sim-kpi-remaining-label", className="sim-kpi-label"),
                                html.Div("—", id="sim-kpi-remaining-val", className="sim-kpi-val"),
                            ],
                            id="sim-kpi-remaining-card",
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
                    id="sim-presets-row",
                    className="sim-presets",
                ),
                html.Div(id="sim-context-text", className="sim-context"),
                html.Div(id="sim-result-text", className="sim-result"),
                dcc.Graph(id="chart-simulation", config={"displayModeBar": False}),
            ],
            className="simulation-section",
        ),
        # Footer
        html.Footer(
            html.Span(id="footer-content"),
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


# ── English Lesehilfe fallback texts ─────────────────────────────────────────
LESEHILFE_FALLBACK_EN = {
    "expand-ts": """#### What does this chart show?
The time series shows the annual deforestation area (km²) measured in the Brazilian Amazon.
Data source: INPE/PRODES (satellite monitoring since 1988). The PRODES year runs August–July.

#### Key message
The Bolsonaro administration (2019–2022) recorded the highest rates since 2006.
With Lula da Silva taking office in Jan 2023, the rate dropped significantly —
clear evidence that political will has direct measurable impact.

#### Background
About 91% of deforestation acts were classified as illegal in 2023/24 (ICV, 2025).
Brazil signed the [Glasgow Leaders' Declaration on Forests](https://www.gov.uk/government/publications/glasgow-leaders-declaration-on-forests-and-land-use-2021-to-2030) (COP26, 2021),
committing to halt illegal deforestation by 2030. The Amazon stores ~123 billion tonnes of carbon (NOAA)
and harbors ~10% of global biodiversity.""",

    "expand-map": """#### What does this chart show?
The animated map shows cumulative forest loss per state from 2010 to the selected year.
Darker red = higher total loss. Each frame adds one year.

#### Key message
Pará and Mato Grosso dominate — both are agribusiness centers (soy, cattle).
The "Arc of Deforestation" — a crescent from Rondônia through Pará to Mato Grosso — is clearly visible.

#### Background
Infrastructure projects (BR-163, Ferrogrão) open previously inaccessible forest areas and advance
the deforestation frontier. Rondônia has already lost over 30% of its original forest —
one of the most severely affected states.""",

    "expand-heatmap": """#### What does this chart show?
The heatmap displays annual deforestation per state as a color matrix.
Each cell represents one state in one year; color intensity encodes the deforested area.

#### Key message
The color pattern makes peaks and high-pressure states visible at a glance.
The Bolsonaro years (2019–2022) clearly show higher intensities across almost all states.

#### Background
Four display modes allow comparison by absolute values (km²), relative intensity
(per 1,000 km²), year-on-year change, and correlation with socio-economic indicators.
Source: INPE PRODES · IBGE.""",

    "expand-donut": """#### What does this chart show?
The pie chart shows the distribution of deforestation across states for the selected year.
The center number shows the total area for that year.

#### Key message
Pará and Mato Grosso regularly account for over 50% of annual deforestation.
This concentration enables targeted interventions with maximum impact.

#### Background
[PRODES monitoring (INPE)](https://terrabrasilis.dpi.inpe.br) uses Landsat/Sentinel data (30m resolution)
and records clearings ≥ 6.25 ha. Smaller degradations from selective logging or fire are recorded
separately by DETER — actual forest degradation exceeds PRODES figures by a factor of 2–3.""",

    "expand-cum": """#### What does this chart show?
The stacked bar chart shows remaining forest capital over time. Green = remaining forest;
dark red = estimated loss before data start; red = measured loss in the dataset.

#### Key message
Combined with historical pre-data loss, total depletion approaches the critical threshold.
[Lovejoy & Nobre (Science Advances, 2018)](https://doi.org/10.1126/sciadv.aat2340) warn:
an irreversible "dieback" threatens at ~20–25% total loss.

#### Background
In a dieback the forest loses the ability to produce its own rainfall, dries out, and transforms
into savanna — even without further logging. Carlos Nobre (INPE) estimates the Amazon has already
lost 15–17% of its original area. Breaching 20–25% would trigger massive, irreversible CO₂ release.""",

    "expand-sankey": """#### What does this diagram show?
The Sankey diagram visualizes deforestation causes (left) and where resulting products flow (right).
Band width is proportional to deforested area — scaled to 10,000 km² as a representative year.

#### Key message
Cattle ranching drives ~75% of deforestation — and most beef is consumed within Brazil.
Soy cultivation (5%) flows predominantly to China. Global consumption patterns directly
influence Amazonian forest loss.

#### Sources & Background
Driver shares: [MapBiomas Annual Report 2024](https://mapbiomas.org/en/annual-deforestation-report) ·
Beef exports: [ABIEC 2024](https://www.abiec.com.br/en/beef-report/) ·
Soy exports: [ABIOVE/ANEC 2023](https://abiove.org.br) ·
CO₂ coefficient: [SEEG 2022](https://seeg.eco.br) (837M tCO₂e / 11,568 km² = 72,300 tCO₂e/km²).
The Amazon Soy Moratorium (2006) curbed direct soy deforestation, but displaced it to pastureland
that indirectly enables soy ("land displacement").""",

    "expand-sim": """#### What does this chart show?
The projection extrapolates the deforestation rate from the latest measurement,
applying the annual change rate linearly into the future.

#### Presets explained
**Paris-compatible (−10%/year):** The minimum pace needed for Brazil's pledge from the
[Glasgow Leaders' Declaration](https://www.gov.uk/government/publications/glasgow-leaders-declaration-on-forests-and-land-use-2021-to-2030) (COP26, 2021) — zero illegal deforestation by 2030.
**Zero 2030 (−30%/year):** The mathematically required maximum for this target.

#### Background
Lula da Silva (in office since Jan 2023) has reactivated enforcement and monitoring.
~91% of deforestation is illegal (ICV, 2025) — effective control would have maximum leverage.
The Amazon stores ~123 billion tonnes of carbon (NOAA) — protecting it is one of the most
cost-effective climate interventions globally.""",

    "expand-treemap":   """#### What does this chart show?
Region → State → Municipality hierarchy. Rectangle size = Amazônia Legal area in km².
Color = deforestation intensity per 1,000 km² (state level). Use the slider or Play to animate year by year.

#### Key message
Pará (PA) and Amazonas (AM) dominate by area, but color reveals which states clear
disproportionately. Rondônia (RO) and Mato Grosso (MT) consistently show high intensity
relative to their size — structural hotspots regardless of year.

#### Background
Shapes are constant across years — only colors change with deforestation pressure.
This separates structural geography (who holds the land) from dynamic pressure
(who is actively clearing it). Source: IBGE · INPE PRODES.""",

    "expand-slope": """#### What does this chart show?
The slope chart shows ranking shifts of states by deforestation area over 2010–2024.
Rank 1 = highest absolute deforestation that year. Crossing lines reveal states gaining or losing relative intensity.

#### Key message
States rising in the ranking show growing pressure; falling states show relative improvement.
Rondônia and Mato Grosso hold consistently high positions — structural hotspots regardless of year.

#### Background
The ranking removes the effect of absolute state size and reveals which states are accelerating
or decelerating their clearing pace over time. Source: INPE PRODES · IBGE.""",

    "expand-scatter": """#### What does this chart show?
The bubble chart compares each state's Amazônia Legal area against cumulative deforestation since 2010.
Bubble size represents state population; the x-axis shows state GDP.

#### Key message
Points above the trend line deforest disproportionately relative to their area or economic output.
Rondônia and Mato Grosso stand out as structural high-pressure states.

#### Background
States with higher GDP per capita tend to show lower relative deforestation —
suggesting that economic development combined with effective governance
can reduce forest degradation pressure. Source: INPE PRODES · IBGE.""",

    "expand-marimekko": """#### What does this chart show?
The Marimekko chart simultaneously shows each state's Amazônia Legal area (bar width)
and the fraction already deforested (red height), combining absolute size and relative intensity.

#### Key message
States with wide bars and a large red fraction combine high area with high destruction rates.
Small percentages can hide enormous absolute losses in large states like Pará.

#### Background
Bar width represents total Amazônia Legal area; red height shows cumulative deforestation
share since 2010. Source: INPE PRODES · IBGE.""",
}

# ── Generate Lesehilfe texts at startup ───────────────────────────────────────
_LESEHILFE_CTX = {
    "expand-ts":      f"Jährliche Entwaldung — Zeitreihe km²/Jahr {min(YEARS)}–{max(YEARS)}, INPE PRODES",
    "expand-map":     f"Entwaldung nach Bundesstaat — Kumulierte animierte Choropleth-Karte {min(YEARS)}–{max(YEARS)}",
    "expand-heatmap": "Entwaldungs-Heatmap — Farbmatrix jährliche Entwaldung je Staat 2010–2024",
    "expand-donut":   "Staatsanteil — Kreisdiagramm Jahresverteilung je Bundesstaat",
    "expand-cum":     f"Kumulativer Waldverlust — Gesamtfläche Amazon 4,1 Mio. km², {min(YEARS)}–{max(YEARS)}",
    "expand-sim":     "Projektion & Szenario-Analyse — Lineare Extrapolation mit Pariser Klimazielen (Glasgow 2021)",
    "expand-sankey":  "Sankey: Entwaldungs-Treiber & globale Absatzmärkte — Rinderzucht 75%, Sojaanbau 5%, Kleinbauern 17%",
}
print("Generating Lesehilfe texts (DE)...")
LESEHILFE: dict[str, str] = {k: _gen_lesehilfe(k, v) for k, v in _LESEHILFE_CTX.items()}
LESEHILFE_EN: dict[str, str] = dict(LESEHILFE_FALLBACK_EN)

# ── Portuguese Lesehilfe (static) ─────────────────────────────────────────────
LESEHILFE_FALLBACK_PT: dict[str, str] = {
    "expand-ts": """#### O que este gráfico mostra?
A série temporal apresenta a área desmatada anualmente (km²) medida na Amazônia brasileira.
Fonte: INPE/PRODES (monitoramento por satélite desde 1988). O ano PRODES vai de agosto a julho.

#### Mensagem principal
O governo Bolsonaro (2019–2022) registrou as maiores taxas desde 2006.
Com a posse de Lula da Silva em jan. de 2023, a taxa caiu significativamente —
prova clara de que a vontade política tem impacto mensurável direto.

#### Contexto
Cerca de 91% dos atos de desmatamento foram classificados como ilegais em 2023/24 (ICV, 2025).
O Brasil assinou a [Declaração de Glasgow sobre Florestas](https://www.gov.uk/government/publications/glasgow-leaders-declaration-on-forests-and-land-use-2021-to-2030) (COP26, 2021),
comprometendo-se a deter o desmatamento ilegal até 2030. A Amazônia armazena ~123 bilhões de toneladas
de carbono (NOAA) e abriga ~10% da biodiversidade global.""",

    "expand-map": """#### O que este gráfico mostra?
O mapa animado exibe a perda florestal acumulada por estado de 2010 até o ano selecionado.
Vermelho mais intenso = maior perda total. Cada quadro da animação acrescenta um ano.

#### Mensagem principal
Pará e Mato Grosso dominam — ambos são centros do agronegócio (soja, pecuária).
O "Arco do Desmatamento" — de Rondônia passando pelo Pará até Mato Grosso — é claramente visível.

#### Contexto
Projetos de infraestrutura (BR-163, Ferrogrão) abrem áreas florestais antes inacessíveis e avançam
a fronteira do desmatamento. Rondônia já perdeu mais de 30% de sua floresta original —
um dos estados mais severamente afetados.""",

    "expand-heatmap": """#### O que este gráfico mostra?
O mapa de calor exibe o desmatamento anual por estado como uma matriz de cores.
Cada célula representa um estado em um determinado ano; a intensidade da cor indica a área desmatada.

#### Mensagem principal
O padrão de cores revela anos de pico e estados de alta atividade de desmatamento simultaneamente.
Os anos do governo Bolsonaro (2019–2022) mostram claramente maiores intensidades em quase todos os estados.

#### Contexto
Os quatro modos de visualização permitem comparar valores absolutos (km²), intensidade relativa
(por 1.000 km²), variação ano a ano e correlação com indicadores socioeconômicos.
Fonte: INPE PRODES · IBGE.""",

    "expand-donut": """#### O que este gráfico mostra?
O gráfico de rosca exibe a distribuição do desmatamento entre os estados para o ano selecionado.
O número central indica a área total desmatada naquele ano.

#### Mensagem principal
Pará e Mato Grosso respondem regularmente por mais de 50% do desmatamento anual.
Essa concentração permite intervenções direcionadas com impacto máximo.

#### Contexto
O [monitoramento PRODES (INPE)](https://terrabrasilis.dpi.inpe.br) utiliza dados Landsat/Sentinel (30m)
e registra desmatamentos ≥ 6,25 ha. Degradações menores são registradas separadamente pelo DETER —
a degradação florestal real supera os dados PRODES por um fator de 2–3.""",

    "expand-cum": """#### O que este gráfico mostra?
O gráfico de barras empilhadas mostra o capital florestal remanescente ao longo do tempo.
Verde = floresta remanescente; vermelho escuro = perda histórica estimada; vermelho = perda medida.

#### Mensagem principal
Combinada com a perda histórica pré-dados, a destruição total se aproxima do limiar crítico.
[Lovejoy & Nobre (Science Advances, 2018)](https://doi.org/10.1126/sciadv.aat2340) alertam:
um "colapso" irreversível ameaça a partir de ~20–25% de perda total.

#### Contexto
No colapso, a floresta perde a capacidade de produzir suas próprias chuvas, seca e se transforma
em savana — mesmo sem novos desmatamentos. Carlos Nobre (INPE) estima que a Amazônia já perdeu
15–17% de sua área original. Ultrapassar os 20–25% desencadearia liberação irreversível de CO₂.""",

    "expand-sankey": """#### O que este diagrama mostra?
O diagrama Sankey visualiza as causas do desmatamento (esquerda) e para onde os produtos gerados fluem (direita).
A largura de cada banda é proporcional à área desmatada — escalada para 10.000 km² como ano representativo.

#### Mensagem principal
A pecuária impulsiona ~75% do desmatamento — e a maior parte da carne bovina é consumida dentro do Brasil.
O cultivo de soja (5%) flui predominantemente para a China. Os padrões de consumo global
influenciam diretamente a perda florestal amazônica.

#### Fontes e Contexto
Participação dos vetores: [MapBiomas Annual Report 2024](https://mapbiomas.org/en/annual-deforestation-report) ·
Exportações de carne: [ABIEC 2024](https://www.abiec.com.br/en/beef-report/) ·
Exportações de soja: [ABIOVE/ANEC 2023](https://abiove.org.br) ·
Coeficiente de CO₂: [SEEG 2022](https://seeg.eco.br) (837 Mi tCO₂e / 11.568 km² = 72.300 tCO₂e/km²).""",

    "expand-sim": """#### O que este gráfico mostra?
A projeção extrapola a taxa de desmatamento a partir da última medição,
aplicando a taxa de variação anual de forma linear no futuro.

#### Presets explicados
**Compatível com Paris (−10%/ano):** O ritmo mínimo necessário para o compromisso do Brasil na
[Declaração de Glasgow](https://www.gov.uk/government/publications/glasgow-leaders-declaration-on-forests-and-land-use-2021-to-2030) (COP26, 2021) — zero desmatamento ilegal até 2030.
**Zero 2030 (−30%/ano):** O máximo matematicamente necessário para atingir essa meta.

#### Contexto
Lula da Silva (no cargo desde jan. de 2023) reativou a fiscalização e o monitoramento.
~91% do desmatamento é ilegal (ICV, 2025) — o controle efetivo teria alavancagem máxima.
A Amazônia armazena ~123 bilhões de toneladas de carbono (NOAA) — protegê-la é uma das
intervenções climáticas mais custo-efetivas do mundo.""",

    "expand-treemap": """#### O que este gráfico mostra?
Hierarquia Região → Estado → Município. Tamanho do retângulo = área na Amazônia Legal em km².
Cor = intensidade do desmatamento por 1.000 km² (nível estadual). Use o controle deslizante ou Play para animar.

#### Mensagem principal
Pará (PA) e Amazonas (AM) dominam pela área, mas a cor revela quais estados desmata
desproporcionalmente. Rondônia (RO) e Mato Grosso (MT) mostram consistentemente alta intensidade
em relação ao tamanho — pontos críticos estruturais, independentemente do ano.

#### Contexto
As formas são constantes ao longo dos anos — apenas as cores mudam com a pressão do desmatamento.
Isso separa a geografia estrutural (quem possui a terra) da pressão dinâmica
(quem está ativamente desmatando). Fonte: IBGE · INPE PRODES.""",

    "expand-slope": """#### O que este gráfico mostra?
O gráfico de inclinação exibe as mudanças no ranking de desmatamento dos estados ao longo de 2010–2024.
Rank 1 = maior desmatamento absoluto no ano. As linhas cruzadas revelam estados que ganharam ou perderam intensidade relativa.

#### Mensagem principal
Estados que sobem no ranking indicam pressão crescente; os que descem mostram melhoria relativa.
Rondônia e Mato Grosso mantêm posições altas de forma consistente — hotspots estruturais.

#### Contexto
O ranking remove o efeito do tamanho absoluto e permite identificar quais estados estão
acelerando ou desacelerando seu ritmo de desmatamento ao longo do tempo.
Fonte: INPE PRODES · IBGE.""",

    "expand-scatter": """#### O que este gráfico mostra?
O gráfico de dispersão compara a área total de cada estado na Amazônia Legal com o desmatamento acumulado desde 2010.
O tamanho da bolha representa a população do estado; o eixo x mostra o PIB estadual.

#### Mensagem principal
Pontos acima da linha de tendência desmatam desproporcionalmente em relação à sua área ou produção econômica.
Rondônia e Mato Grosso se destacam como estados de alta pressão estrutural.

#### Contexto
Estados com maior PIB per capita tendem a mostrar menor desmatamento relativo,
sugerindo que o desenvolvimento econômico combinado com governança efetiva
pode reduzir a pressão sobre a floresta. Fonte: INPE PRODES · IBGE.""",

    "expand-marimekko": """#### O que este gráfico mostra?
O gráfico Marimekko mostra simultaneamente a área total de cada estado na Amazônia Legal (largura da barra)
e a fração já desmatada (altura vermelha), combinando tamanho absoluto e intensidade relativa.

#### Mensagem principal
Estados com barras largas e grande fração vermelha combinam área ampla e alta taxa de destruição.
Percentuais pequenos podem ocultar perdas absolutas enormes em estados grandes como o Pará.

#### Contexto
A largura da barra representa a área total na Amazônia Legal; a parte vermelha indica o percentual
desmatado acumulado desde 2010. Fonte: INPE PRODES · IBGE.""",
}

LESEHILFE_PT: dict[str, str] = dict(LESEHILFE_FALLBACK_PT)
print("✓ Lesehilfe ready")


# ── Clientside callbacks ───────────────────────────────────────────────────────

# Map play / pause via HTML buttons (cleaner than Plotly updatemenus)
clientside_callback(
    """
    function(play_n, pause_n) {
        const ctx = window.dash_clientside.callback_context;
        if (!ctx.triggered.length) return window.dash_clientside.no_update;
        const btn_id = ctx.triggered[0].prop_id.split('.')[0];
        const outer = document.getElementById('chart-map');
        if (!outer) return window.dash_clientside.no_update;
        const el = outer.querySelector('.js-plotly-plot') || outer;
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
    function(map_n, donut_n, sim_n, close_n,
             map_fig, donut_fig, sim_fig) {
        const ctx = window.dash_clientside.callback_context;
        if (!ctx.triggered.length) return [window.dash_clientside.no_update,
                                           {display:'none'}, ''];
        const btn_id = ctx.triggered[0].prop_id.split('.')[0];
        if (btn_id === 'modal-close-btn') {
            return [window.dash_clientside.no_update, {display:'none'}, ''];
        }
        const lookup = {
            'expand-map':   map_fig,
            'expand-donut': donut_fig,
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
    Input("expand-map", "n_clicks"),
    Input("expand-donut", "n_clicks"),
    Input("expand-sim", "n_clicks"),
    Input("modal-close-btn", "n_clicks"),
    State("chart-map", "figure"),
    State("chart-donut", "figure"),
    State("chart-simulation", "figure"),
    prevent_initial_call=True,
)


# ── Colorblind toggle callback ────────────────────────────────────────────────
@callback(
    Output("colorblind-mode", "data"),
    Output("cb-toggle", "className"),
    Input("cb-toggle", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_cb_mode(n):
    active = bool(n % 2) if n else False
    return active, "cb-btn cb-active" if active else "cb-btn"


@callback(
    Output("modal-lesehilfe-content", "children"),
    Output("modal-title", "children"),
    Input("modal-active-chart", "data"),
    Input("lang-toggle", "value"),
    prevent_initial_call=True,
)
def update_modal_lesehilfe(chart_id, lang):
    if not chart_id:
        return "", ""
    titles_de = {
        "expand-ts":        "Jährliche Entwaldung",
        "expand-map":       "Entwaldung nach Bundesstaat",
        "expand-heatmap":   "Entwaldungs-Heatmap",
        "expand-donut":     "Staatsanteil",
        "expand-cum":       "Kumulativer Waldverlust",
        "expand-sim":       "Projektion & Szenario-Analyse",
        "expand-sankey":    "Entwaldungs-Treiber & globale Absatzmärkte",
        "expand-treemap":   "Treemap",
        "expand-slope":     "Entwaldungs-Ranking",
        "expand-scatter":   "Fläche vs. Abholzung",
        "expand-marimekko": "Relativer Waldverlust",
    }
    titles_en = {
        "expand-ts":        "Annual Deforestation",
        "expand-map":       "Deforestation by State",
        "expand-heatmap":   "Deforestation Heatmap",
        "expand-donut":     "State share",
        "expand-cum":       "Cumulative Forest Loss",
        "expand-sim":       "Projection & Scenario Analysis",
        "expand-sankey":    "Deforestation Drivers & Global Markets",
        "expand-treemap":   "Treemap",
        "expand-slope":     "Deforestation Rankings",
        "expand-scatter":   "Size vs. Deforestation",
        "expand-marimekko": "Relative Forest Loss",
    }
    titles_pt = {
        "expand-ts":        "Desmatamento Anual",
        "expand-map":       "Desmatamento por Estado",
        "expand-heatmap":   "Mapa de Calor do Desmatamento",
        "expand-donut":     "Participação por Estado",
        "expand-cum":       "Perda Florestal Acumulada",
        "expand-sim":       "Projeção & Análise de Cenários",
        "expand-sankey":    "Causas do Desmatamento & Mercados Globais",
        "expand-treemap":   "Treemap",
        "expand-slope":     "Ranking de Desmatamento",
        "expand-scatter":   "Área vs. Desmatamento",
        "expand-marimekko": "Perda Florestal Relativa",
    }
    if lang == "de":
        text = LESEHILFE.get(chart_id, "")
        title = titles_de.get(chart_id, "")
    elif lang == "pt":
        text = LESEHILFE_PT.get(chart_id, "")
        title = titles_pt.get(chart_id, "")
    else:
        text = LESEHILFE_EN.get(chart_id, "")
        title = titles_en.get(chart_id, "")
    return dcc.Markdown(text), title


# ── UI Language Callback ──────────────────────────────────────────────────────
@callback(
    Output("label-year", "children"),
    Output("label-state", "children"),
    Output("kpi-total-title", "children"),
    Output("kpi-worst-title", "children"),
    Output("title-ts", "children"),
    Output("sub-ts", "children"),
    Output("title-map", "children"),
    Output("sub-map", "children"),
    Output("title-donut", "children"),
    Output("title-cum", "children"),
    Output("sub-cum", "children"),
    Output("title-sankey", "children"),
    Output("sub-sankey", "children"),
    Output("title-sim", "children"),
    Output("label-rate", "children"),
    Output("label-horizon", "children"),
    Output("sim-kpi-total-label", "children"),
    Output("sim-kpi-remaining-label", "children"),
    Output("sim-context-text", "children"),
    Output("footer-content", "children"),
    Output("header-title", "children"),
    Output("header-subtitle", "children"),
    Output("header-source", "children"),
    Output("filter-state", "options"),
    Output("preset-trend", "children"),
    Output("preset-paris", "children"),
    Output("preset-zero", "children"),
    Output("expand-sim", "children"),
    Output("cb-toggle", "children"),
    Output("title-heatmap", "children"),
    Output("sub-heatmap", "children"),
    Output("heatmap-abs-btn", "children"),
    Output("heatmap-norm-btn", "children"),
    Output("heatmap-corr-btn", "children"),
    Output("heatmap-change-btn", "children"),
    Output("title-treemap", "children"),
    Output("sub-treemap", "children"),
    Output("title-slope", "children"),
    Output("sub-slope", "children"),
    Output("title-scatter", "children"),
    Output("sub-scatter", "children"),
    Input("lang-toggle", "value"),
)
def update_ui_texts(lang):
    tx = T[lang]
    _sankey_suffix = (
        " · Scaled to 10,000 km² · CO₂: 72,000 t CO₂e/km² (" if lang == "en"
        else " · Skaliert auf 10.000 km² · CO₂: 72.000 t CO₂e/km² (" if lang == "de"
        else " · Escalado para 10.000 km² · CO₂: 72.000 t CO₂e/km² ("
    )
    sankey_sub = [
        tx["sub_sankey_prefix"] + _sankey_suffix,
        html.A("SEEG 2022", href="https://seeg.eco.br", target="_blank"),
        "/",
        html.A("INPE", href="https://terrabrasilis.dpi.inpe.br", target="_blank"),
        ") · ",
        html.A("MapBiomas 2024", href="https://mapbiomas.org/en/annual-deforestation-report", target="_blank"),
        " · ",
        html.A("ABIEC 2024", href="https://www.abiec.com.br/en/beef-report/", target="_blank"),
        " · ",
        html.A("ABIOVE/ANEC 2023", href="https://abiove.org.br", target="_blank"),
    ]
    if lang == "en":
        footer = [
            "Primary data: ",
            html.A("INPE PRODES / TerraBrasilis", href="https://terrabrasilis.dpi.inpe.br", target="_blank"),
            " · ",
            html.A("IBGE (State borders)", href="https://servicodados.ibge.gov.br", target="_blank"),
            " · CO₂ emissions: ",
            html.A("SEEG Brasil 2022", href="https://seeg.eco.br", target="_blank"),
            " · Drivers: ",
            html.A("MapBiomas Annual Report 2024", href="https://mapbiomas.org/en/annual-deforestation-report", target="_blank"),
            " · Beef: ",
            html.A("ABIEC Beef Report 2024", href="https://www.abiec.com.br/en/beef-report/", target="_blank"),
            " · Soy: ",
            html.A("ABIOVE/ANEC 2023", href="https://abiove.org.br", target="_blank"),
            " · Research: ",
            html.A("Lovejoy & Nobre, Science Advances 2018", href="https://doi.org/10.1126/sciadv.aat2340", target="_blank"),
            " · ",
            html.A("ICV 2025", href="https://www.icv.org.br", target="_blank"),
        ]
    elif lang == "pt":
        footer = [
            "Dados primários: ",
            html.A("INPE PRODES / TerraBrasilis", href="https://terrabrasilis.dpi.inpe.br", target="_blank"),
            " · ",
            html.A("IBGE (Limites estaduais)", href="https://servicodados.ibge.gov.br", target="_blank"),
            " · Emissões CO₂: ",
            html.A("SEEG Brasil 2022", href="https://seeg.eco.br", target="_blank"),
            " · Causas: ",
            html.A("MapBiomas Annual Report 2024", href="https://mapbiomas.org/en/annual-deforestation-report", target="_blank"),
            " · Carne: ",
            html.A("ABIEC Beef Report 2024", href="https://www.abiec.com.br/en/beef-report/", target="_blank"),
            " · Soja: ",
            html.A("ABIOVE/ANEC 2023", href="https://abiove.org.br", target="_blank"),
            " · Pesquisa: ",
            html.A("Lovejoy & Nobre, Science Advances 2018", href="https://doi.org/10.1126/sciadv.aat2340", target="_blank"),
            " · ",
            html.A("ICV 2025", href="https://www.icv.org.br", target="_blank"),
        ]
    else:
        footer = [
            "Primärdaten: ",
            html.A("INPE PRODES / TerraBrasilis", href="https://terrabrasilis.dpi.inpe.br", target="_blank"),
            " · ",
            html.A("IBGE (Staatsgrenzen)", href="https://servicodados.ibge.gov.br", target="_blank"),
            " · CO₂-Emissionen: ",
            html.A("SEEG Brasil 2022", href="https://seeg.eco.br", target="_blank"),
            " · Treiber: ",
            html.A("MapBiomas Annual Report 2024", href="https://mapbiomas.org/en/annual-deforestation-report", target="_blank"),
            " · Rindfleisch: ",
            html.A("ABIEC Beef Report 2024", href="https://www.abiec.com.br/en/beef-report/", target="_blank"),
            " · Soja: ",
            html.A("ABIOVE/ANEC 2023", href="https://abiove.org.br", target="_blank"),
            " · Forschung: ",
            html.A("Lovejoy & Nobre, Science Advances 2018", href="https://doi.org/10.1126/sciadv.aat2340", target="_blank"),
            " · ",
            html.A("ICV 2025", href="https://www.icv.org.br", target="_blank"),
        ]
    return (
        tx["label_year"], tx["label_state"],
        tx["kpi_total_title"], tx["kpi_worst_title"],
        tx["title_ts"], tx["sub_ts"],
        tx["title_map"], tx["sub_map"],
        tx["title_donut"],
        tx["title_cum"], tx["sub_cum"],
        tx["title_sankey"], sankey_sub,
        tx["title_sim"],
        tx["label_rate"], tx["label_horizon"],
        tx["sim_kpi_total"], tx["sim_kpi_remaining"],
        tx["sim_context"],
        footer,
        tx["header_title"],
        tx["header_subtitle"],
        tx["header_source"],
        [{"label": tx["state_all"], "value": "all"}]
        + [{"label": STATE_NAME_MAP.get(s, s), "value": s} for s in STATES],
        tx["btn_trend"], tx["btn_paris"], tx["btn_zero"], tx["btn_expand"],
        tx["btn_colorblind"],
        tx["title_heatmap"], tx["sub_heatmap"],
        tx["heatmap_abs"], tx["heatmap_norm"], tx["heatmap_corr"],
        tx["heatmap_change"],
        tx["title_treemap"], tx["sub_treemap"],
        tx["title_slope"], tx["sub_slope"],
        tx["title_scatter"], tx["sub_scatter"],
    )


# ── Inline Lesehilfe callback (full-width charts) ─────────────────────────────
@callback(
    Output("lesehilfe-ts", "children"),
    Output("lesehilfe-heatmap", "children"),
    Output("lesehilfe-cum", "children"),
    Output("lesehilfe-treemap", "children"),
    Output("lesehilfe-sankey", "children"),
    Output("lesehilfe-slope", "children"),
    Output("lesehilfe-scatter", "children"),
    Input("lang-toggle", "value"),
)
def update_inline_lesehilfe(lang):
    keys = [
        "expand-ts", "expand-heatmap", "expand-cum",
        "expand-treemap", "expand-sankey", "expand-slope", "expand-scatter",
    ]
    result = []
    for key in keys:
        if lang == "de":
            text = LESEHILFE.get(key, LESEHILFE_FALLBACK.get(key, ""))
        elif lang == "pt":
            text = LESEHILFE_PT.get(key, LESEHILFE_FALLBACK_PT.get(key, ""))
        else:
            text = LESEHILFE_EN.get(key, LESEHILFE_FALLBACK_EN.get(key, ""))
        result.append(dcc.Markdown(text, link_target="_blank"))
    return tuple(result)


# ── Sankey language callback ──────────────────────────────────────────────────
@callback(
    Output("chart-sankey", "figure"),
    Input("lang-toggle", "value"),
)
def update_sankey(lang):
    return _make_sankey_figure(lang)


# ── KPI Callback ─────────────────────────────────────────────────────────────
@callback(
    Output("kpi-year-title", "children"),
    Output("kpi-year-val", "children"),
    Output("kpi-year-sub", "children"),
    Output("kpi-total-val", "children"),
    Output("kpi-total-sub", "children"),
    Output("kpi-worst-val", "children"),
    Output("kpi-worst-sub", "children"),
    Output("kpi-tempo-title", "children"),
    Output("kpi-tempo-val", "children"),
    Output("kpi-tempo-sub", "children"),
    Input("filter-year", "value"),
    Input("filter-class", "value"),
    Input("filter-state", "value"),
    Input("lang-toggle", "value"),
)
def update_kpis(year, cls, state, lang):
    tx = T[lang]
    d = filter_df(year, cls, state)

    # Gerodet aktuelles Jahr
    kpi_year_title = tx["kpi_year_title"](year)
    area_year = d["area_km2"].sum()
    prev_d = filter_df(year - 1, cls, state) if year > min(YEARS) else None
    prev = prev_d["area_km2"].sum() if prev_d is not None else None
    if prev is not None and prev > 0:
        pct = (area_year - prev) / prev * 100
        is_good = pct < 0
        color = "#40916c" if is_good else "#ae2012"
        arrow = "▼" if is_good else "▲"
        vs_prev = "vs. prior year" if lang == "en" else ("ao ano anterior" if lang == "pt" else "zum Vorjahr")
        delta = html.Span(
            [
                html.Span(f"{arrow} ", style={"color": color, "fontWeight": "700", "fontSize": "14px"}),
                f"{fmt_pct(pct, lang)} {vs_prev}",
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
    kpi_total_sub = tx["kpi_total_sub"](fmt_mult(total / GERMANY_AREA_KM2, lang)) if total > 0 else ""

    # Staat mit höchster Rodung
    if state == "all" and len(d) > 0:
        by_st = d.groupby("state_name")["area_km2"].sum()
        worst = by_st.idxmax()
        worst_val = by_st.max()
        kpi_worst_val = state_display(worst)
        cmp = german_comparison(worst_val, lang)
        kpi_worst_sub = tx["kpi_worst_sub"](fmt(worst_val, lang), cmp)
    elif state != "all":
        kpi_worst_val = state_display(state)
        cmp = german_comparison(area_year, lang)
        kpi_worst_sub = tx["kpi_worst_sub"](fmt(area_year, lang), cmp)
    else:
        kpi_worst_val = "—"
        kpi_worst_sub = ""

    # Verlust-Tempo
    kpi_tempo_title = tx["kpi_tempo_title"](year)
    if area_year > 0:
        fields_per_min = (area_year / 365.25 / 24 / 60) / FOOTBALL_FIELD_KM2
        kpi_tempo_val = f"~{fields_per_min:.1f}"
    else:
        kpi_tempo_val = "—"
    kpi_tempo_sub = tx["kpi_tempo_sub"](year)

    return (kpi_year_title, kpi_year_val, delta, kpi_total_val, kpi_total_sub,
            kpi_worst_val, kpi_worst_sub, kpi_tempo_title, kpi_tempo_val, kpi_tempo_sub)


# ── Map Callback — animated Zeitraffer choropleth ─────────────────────────────
@callback(
    Output("chart-map", "figure"),
    Input("filter-class", "value"),
    Input("lang-toggle", "value"),
    Input("colorblind-mode", "data"),
)
def update_map(cls, lang, cb_mode):
    all_years = sorted(df["year"].unique())
    last_year = all_years[-1]
    codes = list(STATE_NAME_MAP.keys())

    # Pre-compute cumulative totals so zmax is the worst-case final value
    d_all = df if cls == "all" else df[df["class_name"] == cls]
    cum_by_state = d_all.groupby(["state_code", "year"])["area_km2"].sum().groupby("state_code").cumsum()
    zmax = float(cum_by_state.max())

    def make_trace(year):
        # Cumulative loss per state UP TO this year — colors only ever get darker
        d = d_all[d_all["year"] <= year]
        by_state = d.groupby("state_code")["area_km2"].sum()
        z_values = [float(by_state.get(c, 0)) for c in codes]
        annual = d_all[d_all["year"] == year].groupby("state_code")["area_km2"].sum()
        tx = T[lang]
        hover_texts = [
            f"<b>{STATE_NAME_MAP[c]}</b><br>"
            f"{tx['map_cum_prefix']} {year}: {by_state.get(c, 0):,.0f} km²<br>"
            f"{tx['map_year_prefix']} {year}: {annual.get(c, 0):,.0f} km²"
            for c in codes
        ]
        active_colorscale = CB_MAP_COLORSCALE if cb_mode else MAP_COLORSCALE
        return go.Choroplethmapbox(
            geojson=STATES_GEO,
            locations=codes,
            z=z_values,
            featureidkey="properties.state_code",
            colorscale=active_colorscale,
            zmin=0, zmax=zmax,
            colorbar=dict(
                title=T[lang]["map_colorbar"], thickness=10, len=0.55,
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
    Output("chart-donut", "figure"),
    Output("chart-donut-sub", "children"),
    Output("chart-cumulative", "figure"),
    Input("filter-year", "value"),
    Input("filter-class", "value"),
    Input("filter-state", "value"),
    Input("lang-toggle", "value"),
    Input("colorblind-mode", "data"),
)
def update_charts(year, cls, state, lang, cb_mode):
    d_all = df.copy()
    if cls != "all":
        d_all = d_all[d_all["class_name"] == cls]
    if state != "all":
        d_all = d_all[d_all["state_name"] == state]

    d_year = filter_df(year, cls, state)

    # ── Zeitreihe — Säulendiagramm mit Datenlabel ─────────────────────────
    ts = d_all.groupby("year")["area_km2"].sum().reset_index()
    max_val = ts["area_km2"].max()
    min_val = ts["area_km2"].min()
    # Bars above avg → graded red; bars below avg → light grey transparent
    avg_for_color = float(ts["area_km2"].mean()) if len(ts) >= 2 else max_val
    above_vals = [v for v in ts["area_km2"] if v >= avg_for_color]
    above_max = max(above_vals) if above_vals else max_val
    above_min = min(above_vals) if above_vals else 0.0
    bar_colors, bar_line_colors, bar_line_widths = [], [], []
    for v in ts["area_km2"]:
        if v >= avg_for_color:
            bar_colors.append(_graded_color(v, above_min, above_max, cb=cb_mode))
            bar_line_colors.append("rgba(0,0,0,0)")
            bar_line_widths.append(0)
        else:
            bar_colors.append("rgba(175,175,175,0.25)")
            bar_line_colors.append("rgba(150,150,150,0.55)")
            bar_line_widths.append(1)
    hover_texts = []
    for _, row in ts.iterrows():
        note = YEAR_NOTES.get(int(row["year"]), "")
        co2_mio = row["area_km2"] * CO2_PER_KM2 / 1e6
        base = (
            f"<b>{int(row['year'])}</b>  {row['area_km2']:,.0f} km²"
            f"<br>≈ {co2_mio:.0f} {T[lang]['ts_co2_unit']}"
        )
        hover_texts.append(base + (f"<br><i>{note}</i>" if note else ""))

    bar_text = [f"{int(v):,}" for v in ts["area_km2"]]
    fig_ts = go.Figure(
        go.Bar(
            x=ts["year"], y=ts["area_km2"],
            marker=dict(
                color=bar_colors,
                line=dict(color=bar_line_colors, width=bar_line_widths),
            ),
            text=bar_text,
            textposition="outside",
            textfont=dict(size=13, color="#444"),
            hovertext=hover_texts,
            hoverinfo="text",
            width=0.88,
        )
    )
    fig_ts.update_layout(
        **{**CHART_LAYOUT, "margin": dict(l=12, r=20, t=12, b=44)},
        xaxis=dict(tickfont=dict(size=12), dtick=1, tickangle=0),
        yaxis=dict(visible=False, range=[0, max_val * 1.28]),
        bargap=0.10,
    )

    # CAGR annotation
    if len(ts) >= 2:
        v_start = float(ts["area_km2"].iloc[0])
        v_end = float(ts["area_km2"].iloc[-1])
        n_years = int(ts["year"].iloc[-1]) - int(ts["year"].iloc[0])
        if v_start > 0 and n_years > 0:
            cagr = (v_end / v_start) ** (1 / n_years) - 1
            cagr_pct = cagr * 100
            sign = "+" if cagr_pct >= 0 else "−"
            cagr_abs = abs(cagr_pct)
            yr_start = int(ts["year"].iloc[0])
            yr_end = int(ts["year"].iloc[-1])
            cagr_lbl = (
                f"CAGR {yr_start}–{yr_end}: {sign}{cagr_abs:.1f} %/Jahr"
                if lang == "de"
                else f"CAGR {yr_start}–{yr_end}: {sign}{cagr_abs:.1f} %/year"
                if lang == "en"
                else f"CAGR {yr_start}–{yr_end}: {sign}{cagr_abs:.1f} %/ano"
            )
            fig_ts.add_annotation(
                x=0.99, y=0.97,
                xref="paper", yref="paper",
                xanchor="right", yanchor="top",
                text=cagr_lbl,
                showarrow=False,
                font=dict(size=12, color="#888", family="Inter"),
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="#ddd",
                borderwidth=1,
                borderpad=6,
            )

    # Average line
    if len(ts) >= 2:
        avg_val = float(ts["area_km2"].mean())
        fig_ts.add_hline(
            y=avg_val,
            line_dash="dash",
            line_color="rgba(210,120,0,0.70)",
            line_width=1.5,
        )
        avg_lbl = (
            f"Ø {fmt(avg_val, lang)}"
            if lang == "de"
            else f"Avg {fmt(avg_val, lang)}"
            if lang == "en"
            else f"Méd {fmt(avg_val, lang)}"
        )
        fig_ts.add_annotation(
            x=0.99, y=avg_val,
            xref="paper",
            text=avg_lbl,
            showarrow=False,
            font=dict(size=11, color="rgba(210,120,0,0.90)", family="Inter"),
            bgcolor="rgba(255,255,255,0.85)",
            xanchor="right",
            yanchor="bottom",
        )

    # ── Staatsanteil Donut — sortiert, Jahreswert in Mitte ────────────────
    all_by_st = d_year.groupby("state_name")["area_km2"].sum().sort_values(ascending=False)
    donut_labels = [state_display(s) for s in all_by_st.index]
    total_year = all_by_st.sum()
    center_text = f"<b>{fmt(total_year, lang, suffix='')}</b><br>km²<br>{year}"
    _active_state_colors = CB_STATE_COLORS if cb_mode else DONUT_COLORS
    fig_donut = go.Figure(
        go.Pie(
            labels=donut_labels,
            values=all_by_st.values,
            hole=0.5,
            marker=dict(
                colors=_active_state_colors[: len(all_by_st)],
                line=dict(color="white", width=2),
            ),
            textposition="inside",
            textfont=dict(size=12),
            hovertemplate="%{label}: %{value:,.0f} km² (%{percent})<extra></extra>",
            direction="clockwise",
            showlegend=False,
        )
    )
    # Dummy scatter traces give full control over legend symbol size
    for i, (lbl_d, col_d) in enumerate(zip(donut_labels, _active_state_colors[: len(all_by_st)])):
        fig_donut.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(symbol="square", size=30, color=col_d),
            name=lbl_d,
            showlegend=True,
            legendrank=i + 1,
        ))
    fig_donut.update_layout(
        **{**CHART_LAYOUT, "showlegend": True, "margin": dict(l=8, r=160, t=8, b=8)},
        legend=dict(
            font=dict(size=20),
            x=1.02, y=0.5, xanchor="left",
            borderwidth=0,
            itemsizing="constant",
            itemwidth=46,
        ),
        xaxis=dict(visible=False, showgrid=False, zeroline=False),
        yaxis=dict(visible=False, showgrid=False, zeroline=False),
        annotations=[dict(
            text=center_text,
            x=0.5, y=0.5,
            font=dict(size=13, family="Inter", color=TEXT),
            showarrow=False,
            align="center",
        )],
    )
    donut_sub = T[lang]["donut_sub"](year)

    # ── Kumulativer Verlust — Vertikales Säulendiagramm (Zeit auf x-Achse) ─
    cum_loss_our = d_all.groupby("year")["area_km2"].sum().cumsum()
    total_loss = AMAZON_LOSS_PREDATA + cum_loss_our
    remaining = AMAZON_FOREST_KM2 - total_loss
    loss_pct = (total_loss / AMAZON_FOREST_KM2 * 100).round(1)

    tx = T[lang]
    if cb_mode:
        _CUM_COLORS = [
            "#009E73",   # remaining — bluish green (colorblind safe)
            "#D55E00",   # pre-2010 loss — vermilion
            "#E69F00",   # post-2010 loss — orange
        ]
    else:
        _CUM_COLORS = [
            "rgba(82,183,136,0.28)",   # remaining — green (= forest still standing)
            "#900000",                 # pre-2010 loss — deepest red
            "rgba(210,0,1,0.62)",      # post-2010 loss — medium red
        ]
    _CUM_NAMES = [tx["cum_leg_remaining"], tx["cum_leg_pre"], tx["cum_leg_post"]]
    fig_cum = go.Figure()
    fig_cum.add_trace(go.Bar(
        x=cum_loss_our.index,
        y=remaining.values,
        name=tx["cum_leg_remaining"],
        marker=dict(color=_CUM_COLORS[0], line=dict(width=0)),
        showlegend=False,
        hovertemplate="<b>%{x}</b><br>" + tx["cum_leg_remaining"] + ": %{y:,.0f} km²<extra></extra>",
    ))
    fig_cum.add_trace(go.Bar(
        x=cum_loss_our.index,
        y=[AMAZON_LOSS_PREDATA] * len(cum_loss_our),
        name=tx["cum_leg_pre"],
        marker=dict(color=_CUM_COLORS[1], line=dict(width=0)),
        showlegend=False,
        hovertemplate="<b>%{x}</b><br>" + tx["cum_leg_pre"] + ": ~700,000 km²<extra></extra>",
    ))
    fig_cum.add_trace(go.Bar(
        x=cum_loss_our.index,
        y=cum_loss_our.values,
        name=tx["cum_leg_post"],
        marker=dict(color=_CUM_COLORS[2], line=dict(width=0)),
        showlegend=False,
        text=[f"{v:.1f}%" for v in loss_pct.values],
        textposition="outside",
        textfont=dict(size=12, color="#555"),
        hovertemplate="<b>%{x}</b><br>" + tx["cum_leg_post"] + ": %{y:,.0f} km²<br>%{customdata:.1f}" + tx["cum_pct_destroyed"] + "<extra></extra>",
        customdata=loss_pct.values,
    ))
    # Dummy scatter traces for larger legend symbols
    for i, (leg_name, leg_color) in enumerate(zip(_CUM_NAMES, _CUM_COLORS)):
        fig_cum.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(symbol="square", size=18, color=leg_color),
            name=leg_name,
            showlegend=True,
            legendrank=i + 1,
        ))
    cum_co2 = float(cum_loss_our.iloc[-1]) * CO2_PER_KM2 / 1e9
    fig_cum.update_layout(
        **{**CHART_LAYOUT, "showlegend": True, "margin": dict(l=60, r=20, t=52, b=44)},
        barmode="stack",
        xaxis_title=tx["cum_axis_year"],
        yaxis_title="km²",
        xaxis=dict(dtick=2, tickmode="linear", tickfont=dict(size=12)),
        yaxis=dict(tickformat=",.0f", tickfont=dict(size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=13)),
        annotations=[dict(
            x=0.5, y=1.10, xref="paper", yref="paper",
            text=tx["cum_annotation"](loss_pct.iloc[-1], min(YEARS), cum_co2),
            showarrow=False,
            font=dict(size=11, color="#888"),
            align="center",
        )],
    )

    return fig_ts, fig_donut, donut_sub, fig_cum


# ── Simulation KPI color helpers ─────────────────────────────────────────────
def _kpi_red_style(frac: float) -> dict:
    """Transparent red tint — intensity grows with frac [0–1], text always dark."""
    frac = max(0.0, min(1.0, frac))
    alpha = round(0.06 + frac * 0.28, 2)   # 0.06 → 0.34
    border_alpha = round(0.12 + frac * 0.36, 2)
    return {"background": f"rgba(144,0,0,{alpha})",
            "border": f"1px solid rgba(144,0,0,{border_alpha})",
            "borderRadius": "4px", "padding": "14px 18px"}


def _kpi_green_style(frac: float) -> dict:
    """Transparent green tint — intensity grows with frac [0–1], text always dark."""
    frac = max(0.0, min(1.0, frac))
    alpha = round(0.06 + frac * 0.28, 2)
    border_alpha = round(0.12 + frac * 0.36, 2)
    return {"background": f"rgba(27,120,55,{alpha})",
            "border": f"1px solid rgba(27,120,55,{border_alpha})",
            "borderRadius": "4px", "padding": "14px 18px"}


_SIM_KPI_DEFAULT_STYLE = {"background": "rgba(144,0,0,0.04)",
                          "border": "1px solid rgba(144,0,0,0.10)",
                          "borderRadius": "4px", "padding": "14px 18px"}


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
        # Filter out anomalously small base years (< 1000 km²) to avoid data artifacts
        rates = [
            (recent[i + 1] - recent[i]) / recent[i] * 100
            for i in range(len(recent) - 1)
            if recent[i] >= 1000
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
    Output("sim-kpi-rate-card", "style"),
    Output("sim-kpi-total-card", "style"),
    Output("sim-kpi-remaining-card", "style"),
    Input("filter-class", "value"),
    Input("filter-state", "value"),
    Input("sim-rate", "value"),
    Input("sim-horizon", "value"),
    Input("lang-toggle", "value"),
    Input("colorblind-mode", "data"),
)
def update_simulation(cls, state, rate_pct, horizon, lang, cb_mode):
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
    tx_sim = T[lang]
    _proj_color = "#D55E00" if cb_mode else RED_MED   # vermilion for CB, red_med for normal
    fig.add_trace(
        go.Scatter(
            x=hist_years, y=hist_vals, name=tx_sim["sim_hist_name"],
            line=dict(color="#64748b", width=2),
            hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
        )
    )
    if proj_vals:
        # Prepend last historical point to connect projection trace to history
        proj_years_conn = [hist_years[-1]] + proj_years
        proj_vals_conn = [hist_vals[-1]] + proj_vals
        fig.add_trace(
            go.Scatter(
                x=proj_years_conn, y=proj_vals_conn, name=tx_sim["sim_proj_name"],
                line=dict(color=_proj_color, width=2, dash="dash"),
                hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
            )
        )
        fig.add_vline(x=max(hist_years), line_dash="dot", line_color="#999", line_width=1)
        final_val = max(0.0, proj_vals[-1])
        fig.add_annotation(
            x=horizon,
            y=final_val,
            text=f"<b>{fmt(final_val, lang)}</b>",
            showarrow=True,
            arrowhead=2,
            arrowcolor=_proj_color,
            ax=44, ay=-28,
            font=dict(size=12, color=_proj_color, family="Inter"),
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor=_proj_color,
            borderwidth=1,
            borderpad=4,
        )

    fig.update_layout(
        **{**CHART_LAYOUT, "showlegend": True},
        yaxis_title=tx_sim["sim_yaxis"],
        xaxis=dict(tickfont=dict(size=12)),
        yaxis=dict(tickfont=dict(size=12), gridcolor="#eeeeea"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=13)),
        transition=dict(duration=600, easing="cubic-in-out"),
    )

    tx = T[lang]
    if proj_vals:
        total_proj = sum(proj_vals)
        total_hist = sum(hist_vals)
        total_all = total_hist + total_proj
        sign = "+" if rate_pct > 0 else "−"
        text = tx["sim_result"](
            sign, fmt_pct(abs(rate_pct), lang), horizon,
            fmt(total_proj, lang), min(hist_years),
            fmt(total_all, lang), fmt_mult(total_all / GERMANY_AREA_KM2, lang),
        )
        kpi_rate_raw = max(0.0, proj_vals[-1])
        kpi_total_raw = total_proj
        full_ts = df.groupby("year")["area_km2"].sum().sort_index()
        full_proj = project_deforestation(
            full_ts.index.tolist(), full_ts.values.tolist(), rate_pct, horizon
        )
        remaining_km2 = (
            AMAZON_FOREST_KM2 - AMAZON_LOSS_PREDATA - float(full_ts.sum()) - sum(full_proj)
        )
        remaining_pct = max(0.0, remaining_km2 / AMAZON_FOREST_KM2 * 100)
        # KPI strings
        kpi_rate = fmt(kpi_rate_raw, lang)
        kpi_total = fmt(kpi_total_raw, lang)
        kpi_remaining = f"{remaining_pct:.1f} %"
        # Dynamic card tint — transparent so text always stays readable
        hist_max = max(float(ts.max()), 1.0)
        rate_frac  = min(1.0, kpi_rate_raw / hist_max)
        total_frac = min(1.0, kpi_total_raw / max(2 * total_hist, 1.0))
        remaining_frac = remaining_pct / 100.0
        rate_card_style      = _kpi_red_style(rate_frac)
        total_card_style     = _kpi_red_style(total_frac)
        remaining_card_style = _kpi_green_style(remaining_frac)
    else:
        text = ("No projection available." if lang == "en"
                else "Nenhuma projeção disponível." if lang == "pt"
                else "Keine Projektion verfügbar.")
        kpi_rate = kpi_total = kpi_remaining = "—"
        rate_card_style = total_card_style = dict(_SIM_KPI_DEFAULT_STYLE)
        remaining_card_style = dict(_SIM_KPI_DEFAULT_STYLE)

    kpi_rate_label = tx["sim_rate_label"](horizon)
    return (fig, text, kpi_rate, kpi_total, kpi_remaining, kpi_rate_label,
            rate_card_style, total_card_style, remaining_card_style)


# ── Heatmap metric toggle callback ────────────────────────────────────────────
_PILL_ACTIVE = "heatmap-pill-active"
_PILL_DEFAULT = ""

@callback(
    Output("heatmap-metric", "data"),
    Output("heatmap-abs-btn", "className"),
    Output("heatmap-norm-btn", "className"),
    Output("heatmap-corr-btn", "className"),
    Output("heatmap-change-btn", "className"),
    Input("heatmap-abs-btn", "n_clicks"),
    Input("heatmap-norm-btn", "n_clicks"),
    Input("heatmap-corr-btn", "n_clicks"),
    Input("heatmap-change-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_heatmap_metric(abs_n, norm_n, corr_n, change_n):
    metric = "abs"
    if ctx.triggered_id == "heatmap-norm-btn":
        metric = "norm"
    elif ctx.triggered_id == "heatmap-corr-btn":
        metric = "corr"
    elif ctx.triggered_id == "heatmap-change-btn":
        metric = "change"
    classes = {k: _PILL_ACTIVE if k == metric else _PILL_DEFAULT for k in ("abs", "norm", "corr", "change")}
    return metric, classes["abs"], classes["norm"], classes["corr"], classes["change"]


# ── Heatmap chart callback ─────────────────────────────────────────────────────
@callback(
    Output("chart-heatmap", "figure"),
    Output("heatmap-corr-panel", "children"),
    Output("heatmap-corr-panel", "style"),
    Input("heatmap-metric", "data"),
    Input("lang-toggle", "value"),
    Input("colorblind-mode", "data"),
)
def update_heatmap(metric, lang, cb_mode):
    _panel_hidden = {"display": "none"}
    _panel_visible = {
        "display": "block",
        "marginTop": "16px",
        "padding": "14px 18px",
        "background": "#f8f8f6",
        "borderLeft": "3px solid #2d6a4f",
        "borderRadius": "0 4px 4px 0",
        "fontSize": "13px",
        "color": "#555",
        "lineHeight": "1.6",
    }
    if df_socio.empty:
        return go.Figure(), None, _panel_hidden

    tx = T[lang]

    # ── Correlation mode: deforestation per 100k population heatmap ──────────
    if metric == "corr":
        d = df_socio[df_socio["year"] <= 2021].copy()

        # State order: ascending cumulative deforestation (same as abs view)
        state_order = (
            d.groupby("state_code")["deforestation_km2"].sum()
            .sort_values(ascending=True).index.tolist()
        )
        years_corr = sorted(d["year"].unique())

        # Build matrix
        z_rows, text_rows, y_labels = [], [], []
        for sc in state_order:
            row, text_row = [], []
            state_rows = d[d["state_code"] == sc]
            # Use state_name for y-label (same as abs view uses state_name)
            state_name = state_rows["state_name"].iloc[0] if not state_rows.empty else sc
            for yr in years_corr:
                yr_row = state_rows[state_rows["year"] == yr]
                val = float(yr_row["defor_per_100k_pop"].iloc[0]) if not yr_row.empty and not yr_row["defor_per_100k_pop"].isna().all() else 0.0
                row.append(val)
                text_row.append(f"{val:.1f}")
            z_rows.append(row)
            text_rows.append(text_row)
            y_labels.append(state_name)

        colorscale = CB_HEATMAP_COLORSCALE if cb_mode else HEATMAP_COLORSCALE
        zmax_val = max((max(r) for r in z_rows), default=1.0)

        x_lbl_c = [str(yr) for yr in years_corr]
        fig = go.Figure(go.Heatmap(
            z=z_rows,
            x=x_lbl_c,
            y=y_labels,
            colorscale=colorscale,
            zmin=0,
            zmax=zmax_val,
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.1f} km²/100k<extra></extra>",
            showscale=True,
            colorbar=dict(title="km²/100k", thickness=10, len=0.75, tickfont=dict(size=11)),
            xgap=1,
            ygap=1,
        ))
        # Dynamic text color: white on dark cells, dark on light cells
        _thr_c = zmax_val * 0.55
        x_sc_c, y_sc_c, txt_sc_c, col_sc_c = [], [], [], []
        for state, z_row, t_row in zip(y_labels, z_rows, text_rows):
            for xv, val, txt in zip(x_lbl_c, z_row, t_row):
                x_sc_c.append(xv)
                y_sc_c.append(state)
                txt_sc_c.append(txt)
                col_sc_c.append("rgba(255,255,255,0.92)" if val > _thr_c else "rgba(30,30,30,0.8)")
        fig.add_trace(go.Scatter(
            x=x_sc_c, y=y_sc_c, mode="text", text=txt_sc_c,
            textfont=dict(size=9, family="Inter", color=col_sc_c),
            showlegend=False, hoverinfo="skip",
        ))
        fig.update_layout(
            **{**CHART_LAYOUT, "margin": dict(l=100, r=80, t=32, b=20)},
            xaxis=dict(tickfont=dict(size=10), side="top"),
            yaxis=dict(tickfont=dict(size=11)),
            height=370,
        )

        panel_content = tx["corr_panel"]
        return fig, panel_content, _panel_visible

    elif metric == "change":
        # Diverging heatmap: % change vs prior year
        d = df_socio.copy()
        # Sort states by cumulative total (same order as abs heatmap)
        state_order = (d.groupby("state_code")["deforestation_km2"].sum()
                       .sort_values(ascending=True).index.tolist())
        # Pivot and compute pct change year-over-year per state
        piv = d.pivot_table(index="state_code", columns="year",
                            values="deforestation_km2").reindex(state_order)
        pct = piv.pct_change(axis=1) * 100  # columns = years, axis=1 = year direction
        # Drop first year (no prior year)
        years_ch = [yr for yr in sorted(piv.columns) if yr > piv.columns.min()]
        pct = pct[years_ch]
        # Average row (all states)
        avg_row = pct.mean(axis=0).to_frame().T
        avg_row.index = [tx["heatmap_total_label"]]
        pct_full = pd.concat([avg_row, pct])
        state_labels = list(pct_full.index)
        year_labels = [str(yr) for yr in years_ch]
        z = pct_full.values.tolist()
        # Clamp to [-100, +100] for colorscale
        z_clamped = [[max(-100, min(100, v)) if v is not None and not (isinstance(v, float) and np.isnan(v)) else 0
                      for v in row] for row in z]
        # Cell text: "+42%" or "−18%"
        text_grid = []
        for row in z:
            text_row = []
            for v in row:
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    text_row.append("")
                else:
                    sign = "+" if v >= 0 else "−"
                    text_row.append(f"{sign}{abs(v):.0f}%")
            text_grid.append(text_row)
        cs = DIVERGING_COLORSCALE
        fig = go.Figure(go.Heatmap(
            z=z_clamped, x=year_labels, y=state_labels,
            colorscale=cs, zmid=0, zmin=-100, zmax=100,
            hovertemplate="<b>%{y}</b> · %{x}<br>Change: %{text}<extra></extra>",
            customdata=text_grid,
            colorbar=dict(title="% change", ticksuffix="%", thickness=14, len=0.8),
        ))
        # Dynamic text color: white on dark cells (high absolute change)
        x_sc_d, y_sc_d, txt_sc_d, col_sc_d = [], [], [], []
        for state, zc_row, t_row in zip(state_labels, z_clamped, text_grid):
            for xv, val, txt in zip(year_labels, zc_row, t_row):
                x_sc_d.append(xv)
                y_sc_d.append(state)
                txt_sc_d.append(txt)
                col_sc_d.append("rgba(255,255,255,0.92)" if abs(val) > 62 else "rgba(30,30,30,0.8)")
        fig.add_trace(go.Scatter(
            x=x_sc_d, y=y_sc_d, mode="text", text=txt_sc_d,
            textfont=dict(size=10, family="Inter", color=col_sc_d),
            showlegend=False, hoverinfo="skip",
        ))
        fig.update_xaxes(side="top", tickfont=dict(size=11))
        fig.update_yaxes(tickfont=dict(size=11), autorange="reversed")
        fig.update_layout(**{**CHART_LAYOUT, "margin": dict(l=100, r=60, t=40, b=20), "height": 370})
        return fig, None, _panel_hidden

    # ── Heatmap mode (abs / norm) ─────────────────────────────────────────────
    col = "defor_per_1000km2" if metric == "norm" else "deforestation_km2"

    # Sort states by cumulative deforestation ascending (lowest at bottom = AP, highest at top = PA)
    cum = df_socio.groupby("state_name")["deforestation_km2"].sum().sort_values(ascending=True)
    state_y = cum.index.tolist()  # AP, TO, AC, ... PA
    years_x = sorted(df_socio["year"].unique())

    total_label = tx["heatmap_total_label"]

    # Build z matrix for states
    z_states = []
    text_states = []
    for state in state_y:
        row = []
        text_row = []
        for yr in years_x:
            rows = df_socio[(df_socio["state_name"] == state) & (df_socio["year"] == yr)]
            val = float(rows[col].iloc[0]) if len(rows) > 0 and not rows[col].isna().all() else 0.0
            row.append(val)
            if metric == "norm":
                text_row.append(f"{val:.1f}")
            else:
                text_row.append(f"{int(val):,}" if val > 0 else "0")
        z_states.append(row)
        text_states.append(text_row)

    # Total row (placed at bottom of heatmap, index 0)
    total_row = []
    total_text = []
    for yr in years_x:
        val = float(df_socio[df_socio["year"] == yr][col].sum())
        total_row.append(val)
        if metric == "norm":
            total_text.append(f"{val:.1f}")
        else:
            total_text.append(f"{int(val):,}")

    # Combine: total first (shown at bottom), then states ascending, PA shown at top
    z_full = [total_row] + z_states
    text_full = [total_text] + text_states
    y_full = [total_label] + state_y

    # zmax based on state values only (not total which would dominate)
    zmax_val = max((max(row) for row in z_states), default=1.0)

    colorscale = CB_HEATMAP_COLORSCALE if cb_mode else HEATMAP_COLORSCALE

    x_lbl = [str(yr) for yr in years_x]
    fig = go.Figure(go.Heatmap(
        z=z_full,
        x=x_lbl,
        y=y_full,
        colorscale=colorscale,
        zmin=0,
        zmax=zmax_val,
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:,.1f}<extra></extra>",
        showscale=True,
        colorbar=dict(thickness=10, len=0.75, tickfont=dict(size=11)),
        xgap=1,
        ygap=1,
    ))
    # Dynamic text color: white on dark cells, dark on light cells
    _threshold = zmax_val * 0.55
    x_sc, y_sc, txt_sc, col_sc = [], [], [], []
    for state, z_row, t_row in zip(y_full, z_full, text_full):
        for xv, val, txt in zip(x_lbl, z_row, t_row):
            x_sc.append(xv)
            y_sc.append(state)
            txt_sc.append(txt)
            col_sc.append("rgba(255,255,255,0.92)" if val > _threshold else "rgba(30,30,30,0.8)")
    fig.add_trace(go.Scatter(
        x=x_sc, y=y_sc, mode="text", text=txt_sc,
        textfont=dict(size=9, family="Inter", color=col_sc),
        showlegend=False, hoverinfo="skip",
    ))

    fig.update_layout(
        **{**CHART_LAYOUT, "margin": dict(l=100, r=80, t=32, b=20)},
        xaxis=dict(tickfont=dict(size=10), side="top"),
        yaxis=dict(tickfont=dict(size=11)),
        height=370,
    )

    return fig, None, _panel_hidden


# ── Treemap callback ──────────────────────────────────────────────────────────
@callback(
    Output("chart-treemap", "figure"),
    Input("lang-toggle", "value"),
    Input("colorblind-mode", "data"),
)
def update_treemap(lang, cb_mode):
    if df_socio.empty or df_dim_state.empty or df_municipality.empty:
        return go.Figure()
    cs = CB_HEATMAP_COLORSCALE if cb_mode else HEATMAP_COLORSCALE

    # Join municipalities with state info (region, state_code)
    state_meta = df_dim_state[["state_id", "state_code", "state_name", "region"]].copy()
    mun = df_municipality.merge(state_meta, on="state_id", how="left")
    mun = mun[mun["area_amazonia_km2"] > 0].copy()

    years_sorted = sorted(df_socio["year"].unique())
    regions = sorted(mun["region"].dropna().unique())
    state_info = mun[["state_code", "state_name", "region"]].drop_duplicates().dropna()

    def _yr_annotation(yr):
        return dict(
            text=f"<b>{yr}</b>",
            x=0.99, y=1.01,
            xref="paper", yref="paper",
            xanchor="right", yanchor="bottom",
            font=dict(size=22, color="#2d6a4f", family="Inter"),
            showarrow=False,
        )

    def _build_trace(yr):
        yr_intensity = (
            df_socio[df_socio["year"] == yr]
            .set_index("state_code")["defor_per_1000km2"]
            .to_dict()
        )
        ids, labels, parents, values, colors = [], [], [], [], []

        # Region nodes
        for region in regions:
            reg_states = state_info[state_info["region"] == region]["state_code"].tolist()
            reg_intensity = float(np.mean([yr_intensity.get(sc, 0) for sc in reg_states]))
            ids.append(f"REG_{region}")
            labels.append(region)
            parents.append("")
            values.append(0.0)
            colors.append(reg_intensity)

        # State nodes
        for _, row in state_info.iterrows():
            sc, region = row["state_code"], row["region"]
            ids.append(f"ST_{sc}")
            labels.append(sc)
            parents.append(f"REG_{region}")
            values.append(0.0)
            colors.append(float(yr_intensity.get(sc, 0)))

        # Municipality nodes
        for _, row in mun.iterrows():
            sc = row["state_code"]
            ids.append(f"MUN_{row['municipality_id']}")
            labels.append(row["municipality_name"])
            parents.append(f"ST_{sc}")
            values.append(float(row["area_amazonia_km2"]))
            colors.append(float(yr_intensity.get(sc, 0)))

        yr_vmax = max(max(colors), 0.1)
        return go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="remainder",
            marker=dict(
                colors=colors,
                colorscale=cs,
                cmin=0, cmax=yr_vmax,
                showscale=True,
                colorbar=dict(title="/ 1k km²", thickness=14, len=0.8),
            ),
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Amazônia area: %{value:,.0f} km²<br>"
                "Deforestation intensity: %{color:.2f} / 1k km²<extra></extra>"
            ),
        ), yr_vmax

    # Build animation frames
    frames = []
    for yr in years_sorted:
        trace, _ = _build_trace(yr)
        frames.append(go.Frame(
            data=[trace],
            name=str(yr),
            layout=go.Layout(annotations=[_yr_annotation(yr)]),
        ))

    # Initial trace (most recent year)
    init_yr = years_sorted[-1]
    init_trace, _ = _build_trace(init_yr)

    fig = go.Figure(data=[init_trace], frames=frames)
    fig.update_layout(
        **{**CHART_LAYOUT, "margin": dict(l=10, r=10, t=44, b=80), "height": 520},
        annotations=[_yr_annotation(init_yr)],
        sliders=[dict(
            active=len(years_sorted)-1,
            steps=[dict(args=[[str(yr)], {"frame": {"duration": 400}, "mode": "immediate"}],
                        label=str(yr), method="animate") for yr in years_sorted],
            x=0.0, len=1.0,
            currentvalue={"visible": False},
            pad={"b": 10, "t": 32},
            font={"family": "Inter", "size": 11, "color": "#999"},
            bgcolor="rgba(255,255,255,0)",
            bordercolor="#ddd",
        )],
    )
    return fig


# ── Treemap animation play/pause (HTML buttons → Plotly.animate) ──────────────
clientside_callback(
    """
    function(play_n, pause_n) {
        const ctx = window.dash_clientside.callback_context;
        if (!ctx.triggered.length) return window.dash_clientside.no_update;
        const btn_id = ctx.triggered[0].prop_id.split('.')[0];
        const outer = document.getElementById('chart-treemap');
        if (!outer) return window.dash_clientside.no_update;
        const el = outer.querySelector('.js-plotly-plot') || outer;
        if (btn_id === 'treemap-play-btn') {
            Plotly.animate(el, null, {
                frame: {duration: 700, redraw: true},
                fromcurrent: true,
                transition: {duration: 300}
            });
        } else {
            try { Plotly.animate(el, [null], {frame: {duration: 0}, mode: 'immediate'}); } catch(e) {}
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("treemap-anim-dummy", "data"),
    Input("treemap-play-btn", "n_clicks"),
    Input("treemap-pause-btn", "n_clicks"),
    prevent_initial_call=True,
)


# ── Slope chart callback ───────────────────────────────────────────────────────
@callback(
    Output("chart-slope", "figure"),
    Input("lang-toggle", "value"),
    Input("colorblind-mode", "data"),
)
def update_slope(lang, cb_mode):
    tx = T[lang]
    if df_socio.empty:
        return go.Figure()
    d = df_socio.copy()
    # Compute rank per year (1 = highest deforestation)
    d["rank"] = d.groupby("year")["deforestation_km2"].rank(ascending=False, method="min").astype(int)
    years_sorted = sorted(d["year"].unique())
    # Line width proportional to avg deforestation
    avg_defor = d.groupby("state_code")["deforestation_km2"].mean()
    max_avg = avg_defor.max()
    states = list(STATE_CAT_COLORS.keys())
    fig = go.Figure()
    for i, sc in enumerate(states):
        sd = d[d["state_code"] == sc].sort_values("year")
        if sd.empty:
            continue
        col = CB_STATE_COLORS[i % len(CB_STATE_COLORS)] if cb_mode else STATE_CAT_COLORS.get(sc, "#888")
        lw = 1.5 + (avg_defor.get(sc, 0) / max_avg) * 3.5
        sn = STATE_NAME_MAP.get(sc, sc)
        # Add line
        fig.add_trace(go.Scatter(
            x=sd["year"], y=sd["rank"],
            mode="lines+markers",
            name=sc,
            line=dict(color=col, width=lw),
            marker=dict(size=6, color=col),
            hovertemplate=f"<b>{sn}</b><br>Year: %{{x}}<br>Rank: %{{y}}<br>Deforested: %{{customdata:,.0f}} km²<extra></extra>",
            customdata=sd["deforestation_km2"].values,
            showlegend=False,
        ))
        # Left label (first year)
        first = sd.iloc[0]
        fig.add_annotation(x=first["year"], y=first["rank"],
                           text=sc, xanchor="right", xshift=-6,
                           showarrow=False, font=dict(size=11, color=col, family="Inter"))
        # Right label (last year)
        last = sd.iloc[-1]
        fig.add_annotation(x=last["year"], y=last["rank"],
                           text=sc, xanchor="left", xshift=6,
                           showarrow=False, font=dict(size=11, color=col, family="Inter"))
    fig.update_yaxes(
        autorange="reversed", tickvals=list(range(1, 10)),
        ticktext=[f"Rank {i}" for i in range(1, 10)],
        showgrid=True, gridcolor="#eeeeea", tickfont=dict(size=11),
        title=None,
    )
    fig.update_xaxes(
        tickvals=years_sorted, ticktext=[str(y) for y in years_sorted],
        tickfont=dict(size=11), showgrid=False, zeroline=False,
    )
    fig.update_layout(
        **{**CHART_LAYOUT, "margin": dict(l=70, r=70, t=20, b=40), "height": 400,
           "plot_bgcolor": "white"},
    )
    return fig


# ── Scatter callback ───────────────────────────────────────────────────────────
@callback(
    Output("chart-scatter", "figure"),
    Input("lang-toggle", "value"),
    Input("colorblind-mode", "data"),
)
def update_scatter(lang, cb_mode):
    tx = T[lang]
    if df_socio.empty or df_dim_state.empty:
        return go.Figure()
    latest_yr = int(df_socio["year"].max())
    d = df_socio[df_socio["year"] == latest_yr].copy()
    d = d.merge(df_dim_state[["state_code", "area_amazonia_km2"]], on="state_code", how="left")
    d = d.dropna(subset=["area_amazonia_km2", "accumulated_km2"])
    x = d["area_amazonia_km2"].values / 1000  # in 1,000 km²
    y = d["accumulated_km2"].values
    pop = d["population"].values
    pop_size = np.sqrt(pop / pop.max()) * 40 + 8
    colors_cat = [STATE_CAT_COLORS.get(sc, "#888") for sc in d["state_code"]]
    if cb_mode:
        colors_cat = [CB_STATE_COLORS[i % len(CB_STATE_COLORS)] for i, _ in enumerate(d["state_code"])]
    # OLS trendline
    coeffs = np.polyfit(x, y, 1)
    x_range = np.linspace(x.min(), x.max(), 100)
    y_trend = np.polyval(coeffs, x_range)
    y_pred = np.polyval(coeffs, x)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    fig = go.Figure()
    # Trendline
    fig.add_trace(go.Scatter(
        x=x_range, y=y_trend,
        mode="lines",
        line=dict(dash="dash", color="#888", width=1.5),
        name=f"OLS (R²={r2:.2f})",
        showlegend=True,
        hoverinfo="skip",
    ))
    # Scatter points
    for _, row in d.iterrows():
        sc = row["state_code"]
        xi = row["area_amazonia_km2"] / 1000
        yi = row["accumulated_km2"]
        sc_keys = list(STATE_CAT_COLORS.keys())
        col = STATE_CAT_COLORS.get(sc, "#888") if not cb_mode else CB_STATE_COLORS[sc_keys.index(sc) % len(CB_STATE_COLORS) if sc in sc_keys else 0]
        ps = float(np.sqrt(row["population"] / pop.max()) * 40 + 8)
        sn = STATE_NAME_MAP.get(sc, sc)
        fig.add_trace(go.Scatter(
            x=[xi], y=[yi],
            mode="markers+text",
            marker=dict(size=ps, color=col, line=dict(width=1, color="white")),
            text=[sc], textposition="top center",
            textfont=dict(size=11, color=col),
            name=sc,
            showlegend=False,
            hovertemplate=(
                f"<b>{sn}</b><br>"
                "Area: %{x:,.0f}k km²<br>"
                "Cumulative deforested: %{y:,.0f} km²<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="State Area in Amazônia Legal (1,000 km²)", tickfont=dict(size=11), gridcolor="#eeeeea")
    fig.update_yaxes(title=f"Cumulative Deforestation 2010–{latest_yr} (km²)", tickfont=dict(size=11), gridcolor="#eeeeea")
    fig.update_layout(
        **{**CHART_LAYOUT, "showlegend": True, "margin": dict(l=70, r=20, t=20, b=50), "height": 420},
    )
    return fig



if __name__ == "__main__":
    app.run(debug=True, port=8050)
