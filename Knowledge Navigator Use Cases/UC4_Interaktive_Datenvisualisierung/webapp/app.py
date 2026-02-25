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
    prev_d = filter_df(year - 1, biome, state) if year > min(YEARS) else None
    prev = prev_d["area_km2"].sum() if prev_d is not None else None
    if prev and prev > 0:
        pct = (area_year - prev) / prev * 100
        delta = f"{'↓' if pct < 0 else '↑'} {abs(pct):.1f}% zum Vorjahr"
    else:
        delta = ""
    kpi_year_val = f"{area_year:,.0f} km²"

    # Kumuliert
    d_all = df.copy()
    if biome != "all":
        d_all = d_all[d_all["biome_name"] == biome]
    if state != "all":
        d_all = d_all[d_all["state_name"] == state]
    total = d_all[d_all["year"] <= year]["area_km2"].sum()
    kpi_total_val = f"{total:,.0f} km²"
    kpi_total_sub = f"≈ {total / 357_114:.1f}× Deutschland" if total > 0 else ""

    # Schlimmster Staat
    if state == "all" and len(d) > 0:
        by_state = d.groupby("state_name")["area_km2"].sum()
        worst = by_state.idxmax()
        worst_val = by_state.max()
        kpi_worst_val = worst
        kpi_worst_sub = f"{worst_val:,.0f} km²"
    elif state != "all":
        kpi_worst_val = state
        kpi_worst_sub = f"{area_year:,.0f} km²"
    else:
        kpi_worst_val = "—"
        kpi_worst_sub = ""

    return kpi_year_val, delta, kpi_total_val, kpi_total_sub, kpi_worst_val, kpi_worst_sub


# ── Charts Callback ───────────────────────────────────────────────────────────
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
    d_all = df.copy()
    if biome != "all":
        d_all = d_all[d_all["biome_name"] == biome]
    if state != "all":
        d_all = d_all[d_all["state_name"] == state]

    # Zeitreihe
    ts = d_all.groupby("year")["area_km2"].sum().reset_index()
    fig_ts = go.Figure(
        go.Scatter(
            x=ts["year"], y=ts["area_km2"],
            mode="lines+markers",
            line=dict(color=GREEN_MED, width=2),
            marker=dict(size=5),
            fill="tozeroy",
            fillcolor="rgba(82,183,136,0.15)",
            hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
        )
    )
    fig_ts.update_layout(**CHART_LAYOUT, yaxis_title="km²", xaxis_title="Jahr")

    # Top 5 Staaten
    d_year = filter_df(year, biome, state)
    by_state = d_year.groupby("state_name")["area_km2"].sum().sort_values(ascending=False)
    top5 = by_state.head(5)
    fig_top = go.Figure(
        go.Bar(
            y=top5.index, x=top5.values,
            orientation="h",
            marker_color=RED_MED,
            hovertemplate="%{y}: %{x:,.0f} km²<extra></extra>",
        )
    )
    fig_top.update_layout(**CHART_LAYOUT, xaxis_title="km²")
    topflop_sub = f"Meiste Entwaldung · {year}"

    # Biom-Vergleich
    biome_data = d_year.groupby("biome_name")["area_km2"].sum().sort_values(ascending=False)
    fig_biome = go.Figure(
        go.Bar(
            x=biome_data.index, y=biome_data.values,
            marker_color=GREEN_MED,
            hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
        )
    )
    fig_biome.update_layout(**CHART_LAYOUT, yaxis_title="km²")

    # Kumulativer Area-Chart
    pivot = d_all.groupby(["year", "biome_name"])["area_km2"].sum().unstack(fill_value=0)
    pivot_cumsum = pivot.cumsum()
    palette = [GREEN_DARK, GREEN_MED, GREEN_LIGHT, "#74c69d", "#b7e4c7", "#d8f3dc"]
    fig_cum = go.Figure()
    for i, col in enumerate(pivot_cumsum.columns):
        fig_cum.add_trace(
            go.Scatter(
                x=pivot_cumsum.index, y=pivot_cumsum[col],
                name=col, mode="lines",
                stackgroup="one",
                line=dict(color=palette[i % len(palette)], width=0.5),
                fillcolor=palette[i % len(palette)],
                hovertemplate=f"{col}: %{{y:,.0f}} km²<extra></extra>",
            )
        )
    cum_layout = {**CHART_LAYOUT, "showlegend": True,
                  "yaxis_title": "km² (kumuliert)", "xaxis_title": "Jahr"}
    fig_cum.update_layout(
        **cum_layout,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return fig_ts, fig_top, topflop_sub, fig_biome, fig_cum


# ── Map Callback ──────────────────────────────────────────────────────────────
@callback(
    Output("layer-raisg", "data"),
    Input("toggle-raisg", "value"),
)
def toggle_raisg(value):
    if value and "show" in value:
        return RAISG_GEO
    return {"type": "FeatureCollection", "features": []}


# ── Simulation Callbacks ──────────────────────────────────────────────────────
@callback(
    Output("sim-rate", "value"),
    Input("preset-trend", "n_clicks"),
    Input("preset-paris", "n_clicks"),
    Input("preset-zero", "n_clicks"),
    prevent_initial_call=True,
)
def apply_preset(trend_clicks, paris_clicks, zero_clicks):
    from dash import ctx
    triggered = ctx.triggered_id
    if triggered == "preset-paris":
        return -10.0
    if triggered == "preset-zero":
        return -30.0
    # Trend: mean rate of last 5 years
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
    Input("filter-biome", "value"),
    Input("filter-state", "value"),
    Input("sim-rate", "value"),
    Input("sim-horizon", "value"),
)
def update_simulation(biome, state, rate_pct, horizon):
    d = df.copy()
    if biome != "all":
        d = d[d["biome_name"] == biome]
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
        fig.add_trace(
            go.Scatter(
                x=proj_years, y=proj_vals, name="Projektion",
                line=dict(color=RED_MED, width=2, dash="dash"),
                hovertemplate="%{x}: %{y:,.0f} km²<extra></extra>",
            )
        )
        fig.add_vline(x=max(hist_years), line_dash="dot", line_color="#999", line_width=1)

    sim_layout = {**CHART_LAYOUT, "showlegend": True}
    fig.update_layout(
        **sim_layout,
        yaxis_title="km²/Jahr",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    if proj_vals:
        total_proj = sum(proj_vals)
        total_hist = sum(hist_vals)
        total_all = total_hist + total_proj
        text = (
            f"Bei {rate_pct:+.1f}%/Jahr: Verlust bis {horizon} = "
            f"{total_proj:,.0f} km² (Projektion) · "
            f"Gesamtverlust seit 2000 = {total_all:,.0f} km² "
            f"(≈ {total_all / 357_114:.1f}× Deutschland)"
        )
    else:
        text = "Keine Projektion verfügbar."

    return fig, text


if __name__ == "__main__":
    app.run(debug=True, port=8050)
