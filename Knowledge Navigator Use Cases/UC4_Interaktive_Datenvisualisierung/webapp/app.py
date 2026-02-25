"""
Amazon Rainforest Deforestation Dashboard
Datenquelle: INPE/PRODES via TerraBrasilis
"""
import json
import os

import dash
import dash_leaflet as dl
import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from data_loader import (
    get_biomes,
    get_states,
    get_years,
    load_deforestation_data,
)
from simulation import cumulative_projection, project_deforestation

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
BIOMES = get_biomes()
STATES = get_states()
LATEST = max(YEARS)

# ── GeoJSON assets ────────────────────────────────────────────────────────────
_assets = os.path.join(os.path.dirname(__file__), "assets")

with open(os.path.join(_assets, "prodes_states.geojson"), encoding="utf-8") as f:
    STATES_GEO = json.load(f)

with open(os.path.join(_assets, "raisg_territories.geojson"), encoding="utf-8") as f:
    RAISG_GEO = json.load(f)

# ── Color palette ─────────────────────────────────────────────────────────────
GREEN_DARK  = "#1a3a2a"
GREEN_MED   = "#2d6a4f"
GREEN_LIGHT = "#52b788"
RED_MED     = "#ae2012"
TEXT        = "#1a1a1a"

CHART_LAYOUT = dict(
    paper_bgcolor="white",
    plot_bgcolor="white",
    font=dict(family="Inter", size=12, color=TEXT),
    margin=dict(l=48, r=16, t=8, b=40),
    showlegend=False,
)

# ── Helpers ──────────────────────────────────────────────────────────────────
def filter_df(year, biome, state):
    d = df[df["year"] == year].copy()
    if biome != "all":
        d = d[d["biome_name"] == biome]
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
        # Header
        html.Header(
            [
                html.Div(
                    [
                        html.H1("Amazon Rainforest"),
                        html.P("Deforestation Monitor · INPE/PRODES 2000–2024"),
                    ],
                    className="header-text",
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
                html.Div(
                    [
                        html.Label("Biom"),
                        dcc.Dropdown(
                            id="filter-biome",
                            options=[{"label": "Alle Biome", "value": "all"}]
                            + [{"label": b, "value": b} for b in BIOMES],
                            value="all",
                            clearable=False,
                        ),
                    ],
                    className="filter-item",
                ),
                html.Div(
                    [
                        html.Label("Staat"),
                        dcc.Dropdown(
                            id="filter-state",
                            options=[{"label": "Alle Staaten", "value": "all"}]
                            + [{"label": s, "value": s} for s in STATES],
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
                make_kpi_card("Gerodet (Jahr)", "kpi-year-val", "kpi-year-sub"),
                make_kpi_card("Kumuliert seit 2000", "kpi-total-val", "kpi-total-sub"),
                make_kpi_card("Schlimmster Staat", "kpi-worst-val", "kpi-worst-sub"),
            ],
            className="kpi-row",
        ),
        # Charts grid
        html.Div(
            [
                # Zeitreihe
                html.Div(
                    [
                        html.H3("Jährliche Entwaldung"),
                        html.Div("km² pro Jahr", className="chart-sub"),
                        dcc.Graph(id="chart-timeseries", config={"displayModeBar": False}),
                    ],
                    className="chart-card",
                ),
                # Leaflet map
                html.Div(
                    [
                        html.H3("Entwaldung nach Bundesstaat"),
                        html.Div(
                            [
                                dcc.Checklist(
                                    id="toggle-raisg",
                                    options=[{"label": "  Indigene Territorien (RAISG)", "value": "show"}],
                                    value=[],
                                    style={"fontSize": "12px"},
                                ),
                            ],
                            className="chart-sub",
                        ),
                        dl.Map(
                            id="map",
                            center=[-5, -55],
                            zoom=4,
                            style={"height": "360px", "borderRadius": "6px"},
                            children=[
                                dl.TileLayer(
                                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                                    attribution="© OpenStreetMap",
                                ),
                                dl.GeoJSON(
                                    id="layer-states",
                                    data=STATES_GEO,
                                    options=dict(
                                        style=dict(weight=1, color="#fff", fillOpacity=0.7, fillColor=GREEN_MED)
                                    ),
                                    hoverStyle=dict(weight=2, color="#333"),
                                    zoomToBounds=True,
                                ),
                                dl.GeoJSON(
                                    id="layer-raisg",
                                    data={"type": "FeatureCollection", "features": []},
                                    options=dict(
                                        style=dict(
                                            weight=1,
                                            color="#e76f51",
                                            fillColor="#e76f51",
                                            fillOpacity=0.25,
                                        )
                                    ),
                                ),
                            ],
                        ),
                    ],
                    className="chart-card",
                ),
                # Top 5 Staaten
                html.Div(
                    [
                        html.H3("Top 5 Staaten"),
                        html.Div(id="chart-topflop-sub", className="chart-sub"),
                        dcc.Graph(id="chart-topflop", config={"displayModeBar": False}),
                    ],
                    className="chart-card",
                ),
                # Biom-Vergleich
                html.Div(
                    [
                        html.H3("Biom-Vergleich"),
                        html.Div("Entwaldung nach Biom", className="chart-sub"),
                        dcc.Graph(id="chart-biome", config={"displayModeBar": False}),
                    ],
                    className="chart-card",
                ),
                # Kumulativer Area-Chart (volle Breite)
                html.Div(
                    [
                        html.H3("Kumulativer Verlust"),
                        html.Div("Aufgestapelt nach Biom, 2000 bis heute", className="chart-sub"),
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
                html.Div(
                    [
                        html.Button("Trend (letzte 5 J.)", id="preset-trend", n_clicks=0),
                        html.Button("Paris-kompatibel", id="preset-paris", n_clicks=0),
                        html.Button("Null 2030", id="preset-zero", n_clicks=0),
                    ],
                    className="sim-presets",
                ),
                html.Div(id="sim-result-text", className="sim-result"),
                dcc.Graph(id="chart-simulation", config={"displayModeBar": False}),
            ],
            className="simulation-section",
        ),
        # Footer
        html.Footer(
            "Daten: INPE PRODES via TerraBrasilis · RAISG (indigene Territorien) · IBGE (Staatsgrenzen)",
            className="footer",
        ),
    ],
    className="dashboard",
)


# ── Callbacks added in Tasks 7, 8, 9, 10 ────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=8050)
