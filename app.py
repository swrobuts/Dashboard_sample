"""
World Happiness Report Dashboard
Überarbeitet nach UI/UX Best Practices
"""

import dash
from dash import dcc, html, Input, Output, callback
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Scipy optional - Fallback wenn nicht verfügbar
try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from data_loader import (
    load_happiness_data,
    get_available_years,
    get_available_regions
)

# ============================================================================
# App Initialisierung
# ============================================================================

app = dash.Dash(
    __name__,
    title="World Happiness Report",
    update_title=None,
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap"
    ],
    suppress_callback_exceptions=True
)

server = app.server

# ============================================================================
# Daten laden
# ============================================================================

df = load_happiness_data()
YEARS = get_available_years()
REGIONS = get_available_regions()

# Letztes Jahr mit vollständigen Faktordaten
YEARS_WITH_FACTORS = [y for y in YEARS if df[(df["year"] == y) & df["gdp"].notna()].shape[0] > 0]
LATEST_FACTOR_YEAR = max(YEARS_WITH_FACTORS) if YEARS_WITH_FACTORS else max(YEARS)

# ============================================================================
# Design System - Konsistente Farbsemantik
# ============================================================================

# Divergierende Skala Rot-Blau für Happiness Score (farbblind-freundlich)
# Skala 2-8: Werte unter 5 = rot (niedrig), über 5 = blau (hoch)
# Bei range_color=[2,8] entspricht 0.5 dem Wert 5
COLOR_SCALE_SEQUENTIAL = [
    [0, "#67001f"],      # Dunkelrot (Score 2) - sehr niedrig
    [0.17, "#b2182b"],   # Rot (Score 3)
    [0.33, "#d6604d"],   # Hell-Rot (Score 4)
    [0.5, "#f7f7f7"],    # Neutral/Weiß (Score 5) - Wendepunkt
    [0.67, "#92c5de"],   # Hell-Blau (Score 6)
    [0.83, "#2166ac"],   # Blau (Score 7)
    [1, "#053061"]       # Dunkelblau (Score 8) - sehr hoch
]

# Divergierende Skala für Korrelationen
COLOR_SCALE_DIVERGING = [
    [0, "#2166ac"],
    [0.5, "#f7f7f7"],
    [1, "#b2182b"]
]

# Kategorische Palette für Ländervergleich (max 5 Länder)
COLOR_COUNTRIES = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b"]

# Regionen - konsistente Zuordnung
REGION_COLORS = {
    "Western Europe": "#1f77b4",
    "North America": "#ff7f0e",
    "Australia and New Zealand": "#2ca02c",
    "Latin America and Caribbean": "#d62728",
    "Eastern Asia": "#9467bd",
    "Southeastern Asia": "#8c564b",
    "Central and Eastern Europe": "#e377c2",
    "Middle East and Northern Africa": "#7f7f7f",
    "Sub-Saharan Africa": "#bcbd22",
    "Southern Asia": "#17becf"
}

COLORS = {
    "text": "#1a1a1a",
    "text_secondary": "#666666",
    "text_muted": "#999999",
    "border": "#e0e0e0",
    "bg": "#f5f5f5",
    "card": "#ffffff",
    "accent": "#2171b5",
    "positive": "#2ca02c",
    "negative": "#d62728",
}

LAYOUT_BASE = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter, sans-serif", "size": 11, "color": COLORS["text"]},
    "margin": {"l": 48, "r": 16, "t": 24, "b": 40},
    "xaxis": {
        "showgrid": False,
        "showline": True,
        "linewidth": 1,
        "linecolor": COLORS["border"],
        "tickfont": {"size": 10},
        "title_font": {"size": 10}
    },
    "yaxis": {
        "showgrid": True,
        "gridwidth": 1,
        "gridcolor": "#f0f0f0",
        "showline": False,
        "tickfont": {"size": 10},
        "title_font": {"size": 10},
        "zeroline": False
    },
    "hoverlabel": {
        "bgcolor": "white",
        "bordercolor": COLORS["border"],
        "font": {"family": "Inter", "size": 11}
    }
}


def get_factor_data(year):
    """Holt Faktordaten mit Fallback auf letztes verfügbares Jahr"""
    data = df[df["year"] == year].copy()
    has_factors = data["gdp"].notna().any()

    if not has_factors and YEARS_WITH_FACTORS:
        fallback_year = LATEST_FACTOR_YEAR
        factor_data = df[df["year"] == fallback_year][
            ["country_name", "gdp", "social_support", "life_expectancy",
             "freedom", "generosity", "corruption"]
        ]
        data = data.drop(
            columns=["gdp", "social_support", "life_expectancy",
                    "freedom", "generosity", "corruption"],
            errors="ignore"
        )
        data = data.merge(factor_data, on="country_name", how="left")
        return data, fallback_year

    return data, year


def calculate_correlation(x, y):
    """Berechnet Pearson-Korrelation mit oder ohne scipy"""
    if SCIPY_AVAILABLE:
        r, p = stats.pearsonr(x, y)
        return r, p
    else:
        # Einfache Korrelationsberechnung ohne scipy
        n = len(x)
        mean_x, mean_y = np.mean(x), np.mean(y)
        std_x, std_y = np.std(x), np.std(y)
        if std_x == 0 or std_y == 0:
            return 0, 1
        r = np.sum((x - mean_x) * (y - mean_y)) / (n * std_x * std_y)
        # p-Wert approximation
        t = r * np.sqrt((n - 2) / (1 - r**2 + 1e-10))
        p = 0.001 if abs(t) > 3.5 else 0.05 if abs(t) > 2 else 0.5
        return r, p


# ============================================================================
# Layout-Komponenten
# ============================================================================

def create_header():
    return html.Div([
        html.Div([
            html.H1("World Happiness Report"),
            html.P("Weltweite Analyse der Lebenszufriedenheit")
        ], className="header-text"),
        html.Div([
            html.Span("Daten: World Happiness Report 2015–2025", className="meta-item"),
            html.Span("·", className="meta-separator"),
            html.Span("Methodik: Gallup World Poll (Cantril-Leiter 0–10)", className="meta-item"),
        ], className="header-meta")
    ], className="dashboard-header")


def create_filters():
    return html.Div([
        html.Div([
            html.Label("Jahr", htmlFor="year-dropdown"),
            dcc.Dropdown(
                id="year-dropdown",
                options=[{"label": str(y), "value": y} for y in YEARS],
                value=max(YEARS),
                clearable=False,
                className="dropdown-minimal"
            )
        ], className="filter-item"),

        html.Div([
            html.Label("Region", htmlFor="region-dropdown"),
            dcc.Dropdown(
                id="region-dropdown",
                options=[{"label": "Alle Regionen", "value": "ALL"}] +
                        [{"label": r, "value": r} for r in REGIONS],
                value="ALL",
                clearable=False,
                className="dropdown-minimal"
            )
        ], className="filter-item filter-region"),

        html.Div([
            html.Label("Ländervergleich (max. 5)", htmlFor="country-dropdown"),
            dcc.Dropdown(
                id="country-dropdown",
                options=[{"label": c, "value": c} for c in sorted(df["country_name"].unique())],
                value=["Finland", "Germany", "United States"],
                multi=True,
                placeholder="Länder auswählen...",
                className="dropdown-minimal"
            )
        ], className="filter-item filter-wide"),
    ], className="filter-bar")


def create_kpi_section():
    return html.Div([
        html.Div(id="kpi-cards", className="kpi-grid"),
        # Hidden store für Statistik-Toggle
        dcc.Store(id="stat-mode", data="mean")
    ])


def create_maximize_button(card_id):
    """Erstellt einen Maximize/Minimize Button für Kacheln"""
    # SVG Icons für Maximize und Minimize
    maximize_icon = html.Div([
        # Maximize Icon (Expand)
        html.Div([
            html.Div(className="maximize-icon", children=[
                html.Span("⛶", style={"fontSize": "14px", "lineHeight": "1"})
            ])
        ], className="icon-expand"),
        # Minimize Icon (Shrink)
        html.Div([
            html.Div(className="minimize-icon", children=[
                html.Span("✕", style={"fontSize": "14px", "lineHeight": "1"})
            ])
        ], className="icon-shrink", style={"display": "none"})
    ])
    return html.Button(
        maximize_icon,
        id={"type": "maximize-btn", "index": card_id},
        className="card-maximize-btn",
        n_clicks=0
    )


# Erklärungstexte für die Charts (nur im maximierten Zustand sichtbar)
CHART_EXPLANATIONS = {
    "map": html.Div([
        html.Div("So lesen Sie diese Karte", className="explanation-title"),
        html.P([
            "Die Weltkarte zeigt den ", html.Strong("Happiness Score"), " (Lebenszufriedenheit) ",
            "für jedes Land. Die Farbskala reicht von ", html.Strong("Rot (niedrig, Score 2-4)"),
            " über ", html.Strong("Weiß (mittel, Score 5)"), " bis ",
            html.Strong("Blau (hoch, Score 6-8)"), "."
        ]),
        html.Ul([
            html.Li("Hovern Sie über ein Land, um Details wie Rang und Region zu sehen"),
            html.Li("Nutzen Sie 'Auswahl/Alle' um zwischen ausgewählten Ländern und der Gesamtansicht zu wechseln"),
            html.Li("Graue Länder haben keine Daten für das gewählte Jahr")
        ])
    ], className="card-explanation"),

    "trend": html.Div([
        html.Div("So lesen Sie dieses Diagramm", className="explanation-title"),
        html.P([
            "Das Liniendiagramm zeigt die ", html.Strong("Entwicklung des Happiness Scores"),
            " über die Jahre für die ausgewählten Länder. Jeder Punkt repräsentiert ",
            "den Score eines Jahres."
        ]),
        html.Ul([
            html.Li("Steigende Linien deuten auf verbesserte Lebenszufriedenheit hin"),
            html.Li("Der rot markierte Bereich zeigt Jahre ohne verfügbare Daten"),
            html.Li("Wählen Sie bis zu 5 Länder im Filter oben aus, um sie zu vergleichen")
        ])
    ], className="card-explanation"),

    "topflop": html.Div([
        html.Div("So lesen Sie dieses Diagramm", className="explanation-title"),
        html.P([
            "Das Balkendiagramm zeigt die ", html.Strong("Top 5 (glücklichsten)"), " und ",
            html.Strong("Flop 5 (unglücklichsten)"), " Länder im gewählten Jahr. ",
            "Die Farben entsprechen der Weltkarten-Farbskala."
        ]),
        html.Ul([
            html.Li("Blaue Balken = hohe Zufriedenheit (Score > 6)"),
            html.Li("Rote Balken = niedrige Zufriedenheit (Score < 5)"),
            html.Li("Bei Filterung nach Region werden die Top/Flop innerhalb dieser Region gezeigt")
        ])
    ], className="card-explanation"),

    "regional": html.Div([
        html.Div("So lesen Sie dieses Diagramm", className="explanation-title"),
        html.P([
            "Das Diagramm zeigt den ", html.Strong("durchschnittlichen Happiness Score"),
            " pro Weltregion. Die Fehlerbalken zeigen die ", html.Strong("Spannweite (Min–Max)"),
            " innerhalb jeder Region."
        ]),
        html.Ul([
            html.Li("Die gepunktete Linie markiert den globalen Durchschnitt"),
            html.Li("Lange Fehlerbalken = große Unterschiede innerhalb der Region"),
            html.Li("Kurze Fehlerbalken = homogene Region mit ähnlichen Werten")
        ])
    ], className="card-explanation"),

    "scatter": html.Div([
        html.Div("So lesen Sie dieses Diagramm", className="explanation-title"),
        html.P([
            "Das Streudiagramm zeigt den Zusammenhang zwischen ",
            html.Strong("Wirtschaftsleistung (BIP pro Kopf, logarithmiert)"), " und ",
            html.Strong("Lebenszufriedenheit"), ". Jeder Punkt ist ein Land."
        ]),
        html.Ul([
            html.Li([html.Strong("r"), " (Korrelationskoeffizient): Stärke des Zusammenhangs (-1 bis +1)"]),
            html.Li([html.Strong("R²"), " (Bestimmtheitsmaß): Anteil der erklärten Varianz (0-100%)"]),
            html.Li("Rote Punkte = ausgewählte Länder, graue Punkte = alle anderen"),
            html.Li("Die gestrichelte Linie zeigt den linearen Trend")
        ])
    ], className="card-explanation"),

    "correlation": html.Div([
        html.Div("So lesen Sie diese Matrix", className="explanation-title"),
        html.P([
            "Die Korrelationsmatrix zeigt, wie stark verschiedene ",
            html.Strong("Faktoren miteinander zusammenhängen"), ". ",
            "Je dunkler das Feld, desto stärker der Zusammenhang."
        ]),
        html.Ul([
            html.Li([html.Strong("+1.00"), " = perfekter positiver Zusammenhang"]),
            html.Li([html.Strong("0.00"), " = kein Zusammenhang"]),
            html.Li([html.Strong("-1.00"), " = perfekter negativer Zusammenhang"]),
            html.Li("Beispiel: Hohe Korrelation zwischen BIP und Lebenserwartung bedeutet, dass wohlhabendere Länder tendenziell höhere Lebenserwartung haben")
        ])
    ], className="card-explanation"),
}


def create_main_grid():
    return html.Div([
        # Overlay für maximierte Kacheln
        html.Div(id="card-overlay", className="card-overlay"),

        # Zeile 1: Karte und Zeitreihe
        html.Div([
            html.Div([
                create_maximize_button("map-card"),
                html.Div([
                    html.Div([
                        html.H3("Happiness Score nach Land"),
                        html.Span(id="map-subtitle", className="chart-subtitle")
                    ], style={"flex": "1"}),
                    # Toggle für Alle/Auswahl
                    html.Div([
                        html.Button("Auswahl", id="btn-map-selection", className="toggle-btn toggle-active"),
                        html.Button("Alle", id="btn-map-all", className="toggle-btn")
                    ], className="toggle-group")
                ], className="chart-header", style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start"}),
                dcc.Store(id="map-mode-store", data="selection"),
                dcc.Graph(id="world-map", config={"displayModeBar": False},
                         style={"height": "320px"}),
                html.Div([
                    html.Span("Skala: 0–10 (dunkel = höher)", className="chart-footnote")
                ], className="chart-footer"),
                CHART_EXPLANATIONS["map"]
            ], className="card", id="map-card"),

            html.Div([
                create_maximize_button("trend-card"),
                html.Div([
                    html.H3("Entwicklung im Zeitverlauf"),
                    html.Span("Ausgewählte Länder", className="chart-subtitle")
                ], className="chart-header"),
                dcc.Graph(id="trend-chart", config={"displayModeBar": False},
                         style={"height": "320px"}),
                html.Div(id="trend-footnote", className="chart-footer"),
                CHART_EXPLANATIONS["trend"]
            ], className="card", id="trend-card"),
        ], className="grid-row-2"),

        # Zeile 2: (1) Top/Flop 5 und (2) Regionale Durchschnitte
        html.Div([
            html.Div([
                create_maximize_button("topflop-card"),
                html.Div([
                    html.H3("Top 5 und Flop 5 Länder"),
                    html.Span(id="topflop-subtitle", className="chart-subtitle")
                ], className="chart-header"),
                dcc.Graph(id="topflop-chart", config={"displayModeBar": False},
                         style={"height": "320px"}),
                CHART_EXPLANATIONS["topflop"]
            ], className="card", id="topflop-card"),

            html.Div([
                create_maximize_button("regional-card"),
                html.Div([
                    html.H3("Regionale Durchschnitte"),
                    html.Span(id="regional-subtitle", className="chart-subtitle")
                ], className="chart-header"),
                dcc.Graph(id="regional-chart", config={"displayModeBar": False},
                         style={"height": "320px"}),
                html.Div([
                    html.Span("Spannweite: Min–Max der Region", className="chart-footnote")
                ], className="chart-footer"),
                CHART_EXPLANATIONS["regional"]
            ], className="card", id="regional-card"),
        ], className="grid-row-2"),

        # Zeile 3: (3) Wohlstand/Zufriedenheit und (4) Korrelation
        html.Div([
            html.Div([
                create_maximize_button("scatter-card"),
                html.Div([
                    html.H3("Wohlstand und Zufriedenheit"),
                    html.Span(id="scatter-subtitle", className="chart-subtitle")
                ], className="chart-header"),
                dcc.Graph(id="scatter-chart", config={"displayModeBar": False},
                         style={"height": "320px"}),
                html.Div(id="scatter-footnote", className="chart-footer"),
                CHART_EXPLANATIONS["scatter"]
            ], className="card", id="scatter-card"),

            html.Div([
                create_maximize_button("correlation-card"),
                html.Div([
                    html.H3("Korrelation der Einflussfaktoren"),
                    html.Span("Über alle Jahre", className="chart-subtitle")
                ], className="chart-header"),
                dcc.Graph(id="correlation-chart", config={"displayModeBar": False},
                         style={"height": "320px"}),
                html.Div([
                    html.Span("Pearson-Korrelation: -1 (negativ) bis +1 (positiv)", className="chart-footnote")
                ], className="chart-footer"),
                CHART_EXPLANATIONS["correlation"]
            ], className="card", id="correlation-card"),
        ], className="grid-row-2"),
    ], className="main-grid")


def create_footer():
    return html.Div([
        html.Div([
            html.Strong("Datenquelle: "),
            html.A("World Happiness Report", href="https://worldhappiness.report/",
                   target="_blank", rel="noopener"),
            html.Span(" · Herausgeber: Sustainable Development Solutions Network")
        ]),
        html.Div([
            html.Strong("Faktoren: "),
            html.Span("BIP (log), Soziale Unterstützung, Lebenserwartung, Freiheit, Großzügigkeit, Korruption")
        ], className="footer-methodology"),
    ], className="footer")


# ============================================================================
# App Layout
# ============================================================================

app.layout = html.Div([
    create_header(),
    html.Div([
        create_filters(),
        create_kpi_section(),
        create_main_grid(),
    ], className="content"),
    create_footer(),
    # Store für Toggle-Status
    dcc.Store(id="stat-mode-store", data="mean")
], className="app-container")


# ============================================================================
# Callbacks
# ============================================================================

@callback(
    Output("kpi-cards", "children"),
    Output("map-subtitle", "children"),
    Output("topflop-subtitle", "children"),
    Input("year-dropdown", "value"),
    Input("region-dropdown", "value"),
    Input("stat-mode-store", "data")
)
def update_kpis(year, region, stat_mode):
    filtered = df[df["year"] == year]
    if region != "ALL":
        filtered = filtered[filtered["region_name"] == region]

    if len(filtered) == 0:
        return [html.Div("Keine Daten verfügbar", className="no-data")], "", ""

    # Vorjahresvergleich
    prev_years = [y for y in YEARS if y < year]
    prev_year = max(prev_years) if prev_years else None
    prev_avg = None
    prev_data = None
    if prev_year:
        prev_data = df[df["year"] == prev_year]
        if region != "ALL":
            prev_data = prev_data[prev_data["region_name"] == region]
        if len(prev_data) > 0:
            prev_avg = prev_data["happiness_score"].mean()

    # Statistiken
    top = filtered.loc[filtered["happiness_score"].idxmax()]
    bottom = filtered.loc[filtered["happiness_score"].idxmin()]
    avg = filtered["happiness_score"].mean()
    median = filtered["happiness_score"].median()
    std = filtered["happiness_score"].std()
    n = len(filtered)

    change = avg - prev_avg if prev_avg else 0

    # Vorjahresrang des Spitzenreiters ermitteln
    top_prev_rank = None
    top_streak = 0
    if prev_data is not None and len(prev_data) > 0:
        prev_sorted = prev_data.sort_values("happiness_score", ascending=False).reset_index(drop=True)
        prev_rank_match = prev_sorted[prev_sorted["country_name"] == top["country_name"]]
        if len(prev_rank_match) > 0:
            top_prev_rank = prev_rank_match.index[0] + 1

    # Wie lange ist das Land schon auf Platz 1?
    for y in sorted(YEARS, reverse=True):
        year_data = df[df["year"] == y]
        if region != "ALL":
            year_data = year_data[year_data["region_name"] == region]
        if len(year_data) > 0:
            year_top = year_data.loc[year_data["happiness_score"].idxmax()]
            if year_top["country_name"] == top["country_name"]:
                top_streak += 1
            else:
                break

    # Abstand zum Durchschnitt berechnen
    top_vs_avg = top["happiness_score"] - avg
    top_vs_avg_pct = (top_vs_avg / avg) * 100 if avg > 0 else 0

    # Spanne zwischen Top und Bottom
    score_gap = top["happiness_score"] - bottom["happiness_score"]

    # Vorjahres-Score des Spitzenreiters für Trend
    top_prev_score = None
    top_score_change = None
    if prev_data is not None and len(prev_data) > 0:
        top_prev_match = prev_data[prev_data["country_name"] == top["country_name"]]
        if len(top_prev_match) > 0:
            top_prev_score = top_prev_match["happiness_score"].values[0]
            top_score_change = top["happiness_score"] - top_prev_score

    # Region des Spitzenreiters
    top_region = top.get("region_name", "")

    region_label = region if region != "ALL" else "Alle Regionen"

    # Erste Kachel: Spitzenreiter mit Kontext
    top_details = []
    top_details.append(html.Span(f"{top['happiness_score']:.2f}", className="score-highlight"))
    top_details.append(html.Span(" von 10"))

    if top_streak > 1:
        top_details.append(html.Span(f" · {top_streak}× in Folge", className="streak-info"))

    # Score-Veränderung zum Vorjahr
    if top_score_change is not None:
        change_icon = "↑" if top_score_change >= 0 else "↓"
        change_class = "positive" if top_score_change >= 0 else "negative"
        top_details.append(html.Br())
        top_details.append(html.Span(
            f"{change_icon} {abs(top_score_change):.2f} zum Vorjahr",
            className=f"rank-change {change_class}"
        ))

    # Abstand zum Durchschnitt
    top_details.append(html.Br())
    top_details.append(html.Span(
        f"+{top_vs_avg:.2f} über Ø ({top_vs_avg_pct:.0f}%)",
        className="avg-distance"
    ))

    cards = [
        html.Div([
            html.Div([
                html.Span("Spitzenreiter", className="kpi-label-text")
            ], className="kpi-label"),
            html.Div(top["country_name"], className="kpi-value kpi-value-text"),
            html.Div([
                html.Span(top_region, className="top-region")
            ] if top_region else [], className="kpi-region"),
            html.Div(top_details, className="kpi-detail"),
            html.Div([
                html.Div([
                    html.Span("Schlusslicht: ", className="bottom-label"),
                    html.Span(f"{bottom['country_name']}", className="bottom-country"),
                    html.Span(f" ({bottom['happiness_score']:.2f})", className="bottom-score")
                ]),
                html.Div([
                    html.Span(f"Spanne: {score_gap:.2f} Punkte", className="gap-info")
                ])
            ], className="kpi-bottom")
        ], className="kpi-card kpi-card-featured"),
    ]

    # Zweite Kachel: Zentrale Tendenz mit Sparkline
    # Berechne Vorjahres-Median für Vergleich
    prev_median = None
    if prev_data is not None and len(prev_data) > 0:
        prev_median = prev_data["happiness_score"].median()

    # Wähle korrekten Wert basierend auf Toggle
    is_mean = stat_mode != "median"
    central_value = avg if is_mean else median
    central_label = "Durchschnitt" if is_mean else "Median"
    prev_central = prev_avg if is_mean else prev_median
    central_change = central_value - prev_central if prev_central else None

    # Quartile berechnen
    q1 = filtered["happiness_score"].quantile(0.25)
    q3 = filtered["happiness_score"].quantile(0.75)
    iqr = q3 - q1
    score_min = filtered["happiness_score"].min()
    score_max = filtered["happiness_score"].max()

    # Gini-Koeffizient berechnen (Maß für Ungleichheit)
    scores_sorted = np.sort(filtered["happiness_score"].values)
    n_scores = len(scores_sorted)
    cumsum = np.cumsum(scores_sorted)
    gini = (2 * np.sum((np.arange(1, n_scores + 1) * scores_sorted))) / (n_scores * np.sum(scores_sorted)) - (n_scores + 1) / n_scores

    # 90/10-Ratio (Verhältnis Top 10% zu Bottom 10%)
    p90 = filtered["happiness_score"].quantile(0.90)
    p10 = filtered["happiness_score"].quantile(0.10)
    ratio_90_10 = p90 / p10 if p10 > 0 else 0

    # Zweite Kachel: Zentrale Tendenz mit Sparkline
    cards.append(html.Div([
        html.Div([
            html.Div([
                html.Button("Ø", id="btn-mean", n_clicks=0,
                           className="toggle-btn toggle-active" if is_mean else "toggle-btn"),
                html.Button("Med", id="btn-median", n_clicks=0,
                           className="toggle-btn" if is_mean else "toggle-btn toggle-active"),
            ], className="stat-toggle"),
            html.Span(central_label, className="kpi-label-text")
        ], className="kpi-label kpi-label-with-toggle"),
        html.Div(f"{central_value:.2f}", id="central-value", className="kpi-value"),
        html.Div([
            html.Span(f"{'↑' if central_change >= 0 else '↓'} {abs(central_change):.2f} zum Vorjahr",
                     className=f"kpi-change {'positive' if central_change >= 0 else 'negative'}")
        ] if central_change is not None else [html.Span("—")], className="kpi-detail"),
        # Sparkline
        dcc.Graph(
            id="sparkline-central",
            config={"displayModeBar": False, "staticPlot": True},
            style={"height": "70px", "marginTop": "8px"}
        ),
        # Erklärung unter der Grafik
        html.Div([
            html.Span(f"Globaler {'Mittelwert' if is_mean else 'Median'} aller Länder im Zeitverlauf",
                     className="chart-footnote")
        ], className="kpi-bottom")
    ], className="kpi-card kpi-card-stats"))

    # Dritte Kachel: Verteilung mit Mini-Boxplot
    region_label_short = region if region != "ALL" else "Alle Länder"
    cards.append(html.Div([
        html.Div([
            html.Span("Verteilung", className="kpi-label-text"),
            html.Span(f" · {n} Länder ({year})", className="boxplot-context")
        ], className="kpi-label"),
        # Violin-Plot - interaktiv mit Hover
        dcc.Graph(
            id="boxplot-mini",
            config={"displayModeBar": False, "staticPlot": False},
            style={"height": "100px", "marginTop": "8px"}
        ),
        html.Div([
            html.Div([
                html.Span("Gini: ", className="metric-label"),
                html.Span(f"{gini:.3f}", className="metric-value"),
                html.Span(" (0=gleich, 1=ungleich)", className="metric-hint")
            ], className="gini-info"),
            html.Div([
                html.Span("90/10-Ratio: ", className="metric-label"),
                html.Span(f"{ratio_90_10:.2f}×", className="metric-value"),
            ], className="ratio-info")
        ], className="distribution-metrics")
    ], className="kpi-card"))

    # Vierte Kachel: Stichprobe mit Kontext und Methodik
    un_members = 193  # UN-Mitgliedsstaaten
    coverage_pct = round(n / un_members * 100)

    cards.append(html.Div([
        html.Div("Stichprobe", className="kpi-label"),
        html.Div(f"{n}", className="kpi-value"),
        html.Div([
            html.Span(f"von {un_members} UN-Staaten", className="kpi-detail"),
            html.Span(f" ({coverage_pct}%)", className="coverage-pct")
        ], style={"display": "flex", "alignItems": "baseline", "gap": "4px"}),

        # Methodik-Info
        html.Div([
            html.Div("Methodik:", className="method-header"),
            html.Ul([
                html.Li("~1.000 Befragte pro Land (Gallup World Poll)"),
                html.Li("Lebenszufriedenheit 0–10 (Cantril-Leiter)"),
                html.Li("Jährliche Erhebung seit 2005")
            ], className="method-list")
        ], className="method-info"),

        html.Div([
            html.Span(f"Zeitraum: {min(YEARS)}–{max(YEARS)}", className="sample-range")
        ], className="kpi-sample-range")
    ], className="kpi-card"))

    return cards, f"{year} · {region_label}", f"{year}"


# Callback für Sparkline
@callback(
    Output("sparkline-central", "figure"),
    Input("year-dropdown", "value"),
    Input("region-dropdown", "value"),
    Input("stat-mode-store", "data")
)
def update_sparkline(year, region, stat_mode):
    """Erstellt Sparkline für zentrale Tendenz über die Jahre"""
    is_mean = stat_mode != "median"
    value_col = "mean" if is_mean else "median"

    # Daten für alle Jahre sammeln
    yearly_stats = []
    for y in sorted(YEARS):
        year_data = df[df["year"] == y]
        if region != "ALL":
            year_data = year_data[year_data["region_name"] == region]
        if len(year_data) > 0:
            yearly_stats.append({
                "year": y,
                "mean": year_data["happiness_score"].mean(),
                "median": year_data["happiness_score"].median()
            })

    if not yearly_stats:
        return go.Figure()

    stats_df = pd.DataFrame(yearly_stats)

    fig = go.Figure()

    # Linie für gewählte Statistik
    fig.add_trace(go.Scatter(
        x=stats_df["year"],
        y=stats_df[value_col],
        mode="lines",
        line=dict(color=COLORS["accent"], width=1.5),
        hoverinfo="skip"
    ))

    # Y-Achsen-Bereich berechnen (beschnitten für bessere Sichtbarkeit)
    y_min = stats_df[value_col].min()
    y_max = stats_df[value_col].max()
    y_padding = (y_max - y_min) * 0.15
    y_range = [y_min - y_padding, y_max + y_padding]

    # Letzten Datenpunkt ermitteln (nicht aktuelles Jahr, sondern letzter verfügbarer Punkt)
    last_year = stats_df["year"].max()
    last_point = stats_df[stats_df["year"] == last_year]
    if len(last_point) > 0:
        last_val = last_point[value_col].values[0]
        # Letzter Datenpunkt in ROT mit Label
        fig.add_trace(go.Scatter(
            x=[last_year],
            y=[last_val],
            mode="markers+text",
            marker=dict(color=COLORS["negative"], size=8, symbol="circle",
                       line=dict(color="white", width=2)),
            text=[f"{last_val:.2f}"],
            textposition="top center",
            textfont=dict(size=9, color=COLORS["negative"], family="Inter"),
            hoverinfo="skip"
        ))

    fig.update_layout(
        margin={"l": 30, "r": 10, "t": 18, "b": 22},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=False,
            showline=True,
            linecolor=COLORS["border"],
            linewidth=1,
            showticklabels=True,
            tickfont={"size": 7, "color": COLORS["text_muted"]},
            tickmode="array",
            # Mehr Jahre anzeigen: alle 2 Jahre + letztes Jahr
            tickvals=[y for y in YEARS if y % 2 == 1 or y == max(YEARS)],
            tickangle=0,
            zeroline=False
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#f0f0f0",
            gridwidth=1,
            showline=True,
            linecolor=COLORS["border"],
            linewidth=1,
            showticklabels=True,
            tickfont={"size": 8, "color": COLORS["text_muted"]},
            range=y_range,
            nticks=3,
            zeroline=False
        ),
        showlegend=False,
        hovermode=False
    )

    return fig


# Callback für Toggle zwischen Durchschnitt und Median
@callback(
    Output("stat-mode-store", "data"),
    Output("btn-mean", "className"),
    Output("btn-median", "className"),
    Input("btn-mean", "n_clicks"),
    Input("btn-median", "n_clicks"),
    prevent_initial_call=True
)
def toggle_stat_mode(mean_clicks, median_clicks):
    """Wechselt zwischen Durchschnitt und Median"""
    from dash import ctx
    triggered = ctx.triggered_id

    if triggered == "btn-mean":
        return "mean", "toggle-btn toggle-active", "toggle-btn"
    else:
        return "median", "toggle-btn", "toggle-btn toggle-active"


# Callback für Mini-Violin/Boxplot
@callback(
    Output("boxplot-mini", "figure"),
    Input("year-dropdown", "value"),
    Input("region-dropdown", "value"),
    Input("country-dropdown", "value")
)
def update_boxplot(year, region, selected_countries):
    """Erstellt Violin-Plot mit interaktiven Datenpunkten und hervorgehobenen Ländern"""
    filtered = df[df["year"] == year].copy()
    if region != "ALL":
        filtered = filtered[filtered["region_name"] == region]

    if len(filtered) == 0:
        return go.Figure()

    # Sicherstellen, dass selected_countries eine Liste ist
    if selected_countries is None:
        selected_countries = []

    fig = go.Figure()

    # Violin-Plot mit kategorialer Y-Position
    fig.add_trace(go.Violin(
        x=filtered["happiness_score"],
        y=[""] * len(filtered),  # Kategoriale Y-Achse
        orientation="h",
        side="both",
        line_color=COLORS["accent"],
        fillcolor="rgba(33, 113, 181, 0.25)",
        meanline_visible=True,
        meanline_color=COLORS["accent"],
        points=False,
        spanmode="soft",
        width=0.8,
        hoverinfo="skip",
        name=""
    ))

    # Datenpunkte für ausgewählte Länder
    selected = filtered[filtered["country_name"].isin(selected_countries)]
    if len(selected) > 0:
        # Rote Punkte auf der Mittellinie - gleiche kategoriale Y-Position
        fig.add_trace(go.Scatter(
            x=selected["happiness_score"].tolist(),
            y=[""] * len(selected),  # Gleiche kategoriale Y-Position wie Violin
            mode="markers",
            marker=dict(
                color="#e74c3c",
                size=10,
                symbol="circle",
                line=dict(color="white", width=1.5),
                opacity=1
            ),
            text=selected["country_name"].tolist(),
            customdata=selected[["happiness_rank", "region_name"]].values.tolist(),
            hovertemplate="<b>%{text}</b><br>" +
                          "Score: %{x:.2f}<br>" +
                          "Rang: %{customdata[0]}<br>" +
                          "Region: %{customdata[1]}<extra></extra>",
            showlegend=False,
            cliponaxis=False
        ))

    fig.update_layout(
        margin={"l": 30, "r": 10, "t": 25, "b": 22},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=True,
            gridcolor="#f0f0f0",
            showline=True,
            linecolor=COLORS["border"],
            linewidth=1,
            tickfont={"size": 8, "color": COLORS["text_muted"]},
            range=[0, 10],
            dtick=2
        ),
        yaxis=dict(
            showgrid=False,
            showline=False,
            showticklabels=False,
            zeroline=False
        ),
        showlegend=False,
        hovermode="closest"
    )

    return fig


# Callback für Karten-Toggle
@callback(
    Output("map-mode-store", "data"),
    Output("btn-map-selection", "className"),
    Output("btn-map-all", "className"),
    Input("btn-map-selection", "n_clicks"),
    Input("btn-map-all", "n_clicks"),
    prevent_initial_call=True
)
def toggle_map_mode(sel_clicks, all_clicks):
    """Wechselt zwischen Auswahl und Alle Länder"""
    from dash import ctx
    triggered = ctx.triggered_id

    if triggered == "btn-map-selection":
        return "selection", "toggle-btn toggle-active", "toggle-btn"
    else:
        return "all", "toggle-btn", "toggle-btn toggle-active"


@callback(
    Output("world-map", "figure"),
    Input("year-dropdown", "value"),
    Input("region-dropdown", "value"),
    Input("country-dropdown", "value"),
    Input("map-mode-store", "data")
)
def update_map(year, region, selected_countries, map_mode):
    """Choropleth mit verbesserter Farbskala"""
    filtered = df[df["year"] == year].copy()
    if region != "ALL":
        filtered = filtered[filtered["region_name"] == region]

    # Bei "selection" nur ausgewählte Länder zeigen
    if map_mode == "selection" and selected_countries:
        filtered = filtered[filtered["country_name"].isin(selected_countries)]

    # Falls keine Daten, leere Karte
    if len(filtered) == 0:
        fig = go.Figure(go.Scattergeo())
        fig.update_layout(
            geo=dict(
                showframe=False,
                projection_type="natural earth",
                bgcolor="rgba(0,0,0,0)",
                showland=True,
                landcolor="#f0f0f0"
            ),
            margin={"l": 0, "r": 0, "t": 0, "b": 0},
            paper_bgcolor="rgba(0,0,0,0)"
        )
        return fig

    fig = px.choropleth(
        filtered,
        locations="iso_alpha",
        color="happiness_score",
        hover_name="country_name",
        hover_data={
            "iso_alpha": False,
            "happiness_score": False,
            "happiness_rank": False,
            "region_name": False
        },
        color_continuous_scale=COLOR_SCALE_SEQUENTIAL,
        range_color=[2, 8],
        labels={
            "happiness_score": "Score",
            "happiness_rank": "Rang",
            "region_name": "Region"
        }
    )

    # Benutzerdefinierter Hover mit besserer Lesbarkeit
    fig.update_traces(
        hovertemplate="<b style='font-size:14px'>%{hovertext}</b><br><br>" +
                      "<b>Score:</b> %{z:.2f}<br>" +
                      "<b>Rang:</b> %{customdata[0]}<br>" +
                      "<b>Region:</b> %{customdata[1]}<extra></extra>",
        customdata=filtered[["happiness_rank", "region_name"]].values
    )

    fig.update_layout(
        **{k: v for k, v in LAYOUT_BASE.items() if k not in ["xaxis", "yaxis", "margin", "hoverlabel"]},
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        geo=dict(
            showframe=False,
            showcoastlines=True,
            coastlinecolor="#cccccc",
            projection_type="natural earth",
            bgcolor="rgba(0,0,0,0)",
            showland=True,
            landcolor="#f0f0f0",
            showocean=True,
            oceancolor="#ffffff",
            showcountries=True,
            countrycolor="#e0e0e0",
            countrywidth=0.5
        ),
        coloraxis_colorbar=dict(
            title="Score",
            title_font={"size": 10},
            thickness=10,
            len=0.6,
            tickfont={"size": 9},
            tickvals=[2, 4, 6, 8],
            outlinewidth=0,
            x=1.01
        ),
        hoverlabel=dict(
            bgcolor="white",
            font_size=12,
            font_family="Inter, sans-serif",
            font_color="#1a1a1a",
            bordercolor="#e0e0e0"
        )
    )

    return fig


@callback(
    Output("topflop-chart", "figure"),
    Input("year-dropdown", "value"),
    Input("region-dropdown", "value")
)
def update_topflop(year, region):
    """Top 5 und Flop 5 Länder als horizontales Balkendiagramm"""
    filtered = df[df["year"] == year].copy()
    if region != "ALL":
        filtered = filtered[filtered["region_name"] == region]

    if len(filtered) < 10:
        # Weniger als 10 Länder: zeige alle
        combined = filtered.sort_values("happiness_score", ascending=True)
    else:
        # Top 5 und Flop 5
        top5 = filtered.nlargest(5, "happiness_score")
        flop5 = filtered.nsmallest(5, "happiness_score")
        combined = pd.concat([flop5, top5]).drop_duplicates()
        combined = combined.sort_values("happiness_score", ascending=True)

    # Farben direkt aus der Weltkarten-Farbskala (COLOR_SCALE_SEQUENTIAL)
    # Score 2-8 wird auf die gleiche Skala gemappt
    def score_to_color(score):
        # Normalisieren auf 0-1 (Bereich 2-8)
        norm = (score - 2) / 6
        norm = max(0, min(1, norm))

        # Exakt die gleichen Farben wie COLOR_SCALE_SEQUENTIAL
        # [0, "#67001f"], [0.17, "#b2182b"], [0.33, "#d6604d"],
        # [0.5, "#f7f7f7"], [0.67, "#92c5de"], [0.83, "#2166ac"], [1, "#053061"]
        if norm <= 0.17:
            return "#67001f"   # Dunkelrot (Score ~2-3)
        elif norm <= 0.33:
            return "#b2182b"   # Rot (Score ~3-4)
        elif norm <= 0.5:
            return "#d6604d"   # Hell-Rot (Score ~4-5)
        elif norm <= 0.67:
            return "#92c5de"   # Hell-Blau (Score ~5-6)
        elif norm <= 0.83:
            return "#2166ac"   # Blau (Score ~6-7)
        else:
            return "#053061"   # Dunkelblau (Score ~7-8)

    colors = [score_to_color(s) for s in combined["happiness_score"]]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=combined["happiness_score"],
        y=combined["country_name"],
        orientation="h",
        marker_color=colors,
        text=[f"{s:.2f}" for s in combined["happiness_score"]],
        textposition="outside",
        textfont={"size": 10},
        hovertemplate="<b>%{y}</b><br>Score: %{x:.2f}<extra></extra>"
    ))

    fig.update_layout(
        **{k: v for k, v in LAYOUT_BASE.items() if k not in ["margin", "hoverlabel"]},
        margin={"l": 120, "r": 50, "t": 16, "b": 40},
        xaxis_title="Happiness Score",
        xaxis_range=[0, 8.5],
        yaxis_title="",
        showlegend=False,
        hoverlabel=dict(
            bgcolor="white",
            font_size=12,
            font_family="Inter, sans-serif",
            font_color="#1a1a1a",
            bordercolor="#e0e0e0"
        )
    )

    return fig


@callback(
    Output("trend-chart", "figure"),
    Output("trend-footnote", "children"),
    Input("country-dropdown", "value")
)
def update_trends(countries):
    """Zeitreihe mit Y-Achse bei 0 und Datenlücken-Markierung"""
    # Fallback wenn keine Länder ausgewählt
    if not countries:
        countries = ["Finland", "Germany"]

    countries = countries[:5]

    filtered = df[df["country_name"].isin(countries)].sort_values(["country_name", "year"])

    # Prüfen ob überhaupt Daten vorhanden
    if len(filtered) == 0:
        # Fallback: Zeige Top-3 Länder des letzten Jahres
        latest_year = max(YEARS)
        top_countries = df[df["year"] == latest_year].nlargest(3, "happiness_score")["country_name"].tolist()
        if top_countries:
            countries = top_countries
            filtered = df[df["country_name"].isin(countries)].sort_values(["country_name", "year"])

    # Wenn immer noch keine Daten, zeige Hinweis
    if len(filtered) == 0:
        fig = go.Figure()
        fig.update_layout(
            **{k: v for k, v in LAYOUT_BASE.items() if k not in ["xaxis", "yaxis"]},
            annotations=[dict(
                text="Keine Daten für ausgewählte Länder verfügbar",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=12, color=COLORS["text_muted"])
            )]
        )
        return fig, html.Span("Bitte andere Länder auswählen", className="chart-footnote warning")

    fig = go.Figure()

    # Datenlücke 2024 markieren
    has_2024_gap = 2024 not in YEARS and 2023 in YEARS and 2025 in YEARS

    if has_2024_gap:
        fig.add_vrect(
            x0=2023.5, x1=2024.5,
            fillcolor="#fee2e2",
            opacity=0.5,
            line_width=0,
            annotation_text="keine Daten",
            annotation_position="top",
            annotation_font_size=9,
            annotation_font_color="#999"
        )

    # Y-Achsen-Bereich dynamisch berechnen (beschnitten für bessere Lesbarkeit)
    all_scores = filtered["happiness_score"]
    y_min = max(0, all_scores.min() - 0.5)
    y_max = min(10, all_scores.max() + 0.5)
    # Auf halbe Zahlen runden
    y_min = np.floor(y_min * 2) / 2
    y_max = np.ceil(y_max * 2) / 2

    for i, country in enumerate(countries):
        country_data = filtered[filtered["country_name"] == country]

        # Nur Länder mit Daten hinzufügen
        if len(country_data) > 0:
            fig.add_trace(go.Scatter(
                x=country_data["year"],
                y=country_data["happiness_score"],
                mode="markers",  # Nur Punkte, keine Linien
                name=country,
                marker=dict(
                    size=12,
                    color=COLOR_COUNTRIES[i % len(COLOR_COUNTRIES)],
                    line=dict(color="white", width=1)
                ),
                hovertemplate=f"<b>{country}</b><br>%{{x}}: %{{y:.2f}}<extra></extra>"
            ))

    # Layout ohne doppelte xaxis/yaxis/hoverlabel
    base_layout = {k: v for k, v in LAYOUT_BASE.items() if k not in ["xaxis", "yaxis", "margin", "hoverlabel"]}

    fig.update_layout(
        **base_layout,
        margin={"l": 48, "r": 16, "t": 24, "b": 40},
        xaxis=dict(
            showgrid=True,
            gridcolor="#f0f0f0",
            showline=True,
            linewidth=1,
            linecolor=COLORS["border"],
            tickfont={"size": 10},
            title="",
            tickmode="array",
            tickvals=YEARS
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor="#f0f0f0",
            showline=False,
            tickfont={"size": 10},
            title="Score",
            title_font={"size": 10},
            zeroline=False,
            range=[y_min, y_max]
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font={"size": 10}
        ),
        hovermode="closest",
        hoverlabel=dict(
            bgcolor="white",
            font_size=12,
            font_family="Inter, sans-serif",
            font_color="#1a1a1a",
            bordercolor="#e0e0e0"
        )
    )

    # Footnote
    if has_2024_gap:
        footnote = html.Span("2024: Keine Daten verfügbar", className="chart-footnote warning")
    else:
        footnote = html.Span(f"Y-Achse: {y_min:.1f}–{y_max:.1f}", className="chart-footnote")

    return fig, footnote


@callback(
    Output("scatter-chart", "figure"),
    Output("scatter-subtitle", "children"),
    Output("scatter-footnote", "children"),
    Input("year-dropdown", "value"),
    Input("region-dropdown", "value"),
    Input("country-dropdown", "value")
)
def update_scatter(year, region, selected_countries):
    """Scatterplot mit Trendlinie und R² - ausgewählte Länder hervorgehoben"""
    data, factor_year = get_factor_data(year)

    if region != "ALL":
        data = data[data["region_name"] == region]

    data = data[data["gdp"].notna() & (data["gdp"] > 0)].copy()

    if selected_countries is None:
        selected_countries = []

    subtitle = f"Daten: {factor_year}"
    if factor_year != year:
        subtitle += f" (Faktoren aus {factor_year})"

    if len(data) < 3:
        fig = go.Figure()
        fig.update_layout(
            **LAYOUT_BASE,
            annotations=[dict(
                text="Zu wenig Daten für Analyse",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=12, color=COLORS["text_muted"])
            )]
        )
        return fig, subtitle, ""

    # Korrelation berechnen
    r, p_value = calculate_correlation(data["gdp"].values, data["happiness_score"].values)
    r_squared = r ** 2

    fig = go.Figure()

    # Nicht-ausgewählte Länder (grau, im Hintergrund)
    other_data = data[~data["country_name"].isin(selected_countries)]
    if len(other_data) > 0:
        fig.add_trace(go.Scatter(
            x=other_data["gdp"],
            y=other_data["happiness_score"],
            mode="markers",
            marker=dict(
                size=8,
                color="#666666",
                line=dict(width=1, color="white"),
                opacity=0.6
            ),
            text=other_data["country_name"],
            customdata=other_data[["region_name"]].values,
            hovertemplate="<b>%{text}</b><br>BIP: %{x:.2f}<br>Score: %{y:.2f}<br>Region: %{customdata[0]}<extra></extra>",
            showlegend=False
        ))

    # Ausgewählte Länder (rot, hervorgehoben)
    selected_data = data[data["country_name"].isin(selected_countries)]
    if len(selected_data) > 0:
        fig.add_trace(go.Scatter(
            x=selected_data["gdp"],
            y=selected_data["happiness_score"],
            mode="markers",
            marker=dict(
                size=12,
                color="#e74c3c",
                line=dict(width=2, color="white")
            ),
            text=selected_data["country_name"],
            customdata=selected_data[["region_name"]].values,
            hovertemplate="<b>%{text}</b><br>BIP: %{x:.2f}<br>Score: %{y:.2f}<br>Region: %{customdata[0]}<extra></extra>",
            showlegend=False
        ))

    # Trendlinie
    z = np.polyfit(data["gdp"], data["happiness_score"], 1)
    p = np.poly1d(z)
    x_line = np.linspace(data["gdp"].min(), data["gdp"].max(), 50)

    fig.add_trace(go.Scatter(
        x=x_line, y=p(x_line),
        mode="lines",
        line=dict(color="#999999", width=2, dash="dash"),
        hoverinfo="skip",
        showlegend=False
    ))

    fig.update_layout(
        **{k: v for k, v in LAYOUT_BASE.items() if k != "hoverlabel"},
        xaxis_title="BIP pro Kopf (log.)",
        yaxis_title="Happiness Score",
        yaxis_range=[0, 10],
        showlegend=False,
        hoverlabel=dict(
            bgcolor="white",
            font_size=12,
            font_family="Inter, sans-serif",
            font_color="#1a1a1a",
            bordercolor="#e0e0e0"
        )
    )

    footnote = html.Span([
        f"r = {r:.2f}, R² = {r_squared:.2f} ",
        html.Span(f"(p < 0.001)" if p_value < 0.001 else f"(p = {p_value:.3f})",
                  className="stat-detail")
    ], className="chart-footnote")

    return fig, subtitle, footnote


@callback(
    Output("correlation-chart", "figure"),
    Input("year-dropdown", "value")
)
def update_correlation(_year):
    """Korrelationsmatrix der Einflussfaktoren über alle Jahre"""
    # Nur Jahre mit Faktordaten verwenden
    factor_data = df[df["year"].isin(YEARS_WITH_FACTORS)].copy()

    factors = ["happiness_score", "gdp", "social_support", "life_expectancy",
               "freedom", "generosity", "corruption"]
    factor_labels = ["Glücklichkeit", "BIP", "Soziale Unterstützung",
                     "Lebenserwartung", "Freiheit", "Großzügigkeit", "Korruption"]

    # Korrelationsmatrix berechnen
    corr_data = factor_data[factors].dropna()

    if len(corr_data) < 10:
        fig = go.Figure()
        fig.update_layout(
            **LAYOUT_BASE,
            annotations=[dict(
                text="Nicht genug Daten für Korrelationsanalyse",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=12, color=COLORS["text_muted"])
            )]
        )
        return fig

    # Pearson-Korrelation berechnen
    corr_matrix = corr_data.corr(method="pearson")

    # Grau-Skala: Stärke der Korrelation (absoluter Wert) bestimmt Dunkelheit
    # Weiß = keine Korrelation (0), Dunkelgrau = starke Korrelation (±1)
    # Für positive/negative Unterscheidung: Textfarbe anpassen
    abs_corr = np.abs(corr_matrix.values)

    # Heatmap mit Grau-Skala (Intensität = Stärke der Korrelation)
    fig = go.Figure(data=go.Heatmap(
        z=abs_corr,
        x=factor_labels,
        y=factor_labels,
        colorscale=[[0, "#ffffff"], [0.3, "#e0e0e0"], [0.6, "#999999"], [1, "#333333"]],
        zmin=0,
        zmax=1,
        text=np.round(corr_matrix.values, 2),
        texttemplate="%{text}",
        textfont={"size": 10},
        hovertemplate="%{y} vs %{x}<br>r = %{text}<extra></extra>",
        colorbar=dict(
            title="|r|",
            thickness=10,
            len=0.8,
            tickvals=[0, 0.25, 0.5, 0.75, 1],
            ticktext=["0", "0.25", "0.5", "0.75", "1"],
            tickfont={"size": 9}
        )
    ))

    fig.update_layout(
        **{k: v for k, v in LAYOUT_BASE.items() if k not in ["xaxis", "yaxis", "margin", "hoverlabel"]},
        margin={"l": 140, "r": 20, "t": 16, "b": 100},
        xaxis=dict(
            tickangle=-45,
            tickfont={"size": 10},
            side="bottom"
        ),
        yaxis=dict(
            tickfont={"size": 10},
            autorange="reversed"
        ),
        hoverlabel=dict(
            bgcolor="white",
            font_size=12,
            font_family="Inter, sans-serif",
            font_color="#1a1a1a",
            bordercolor="#e0e0e0"
        )
    )

    return fig


@callback(
    Output("regional-chart", "figure"),
    Output("regional-subtitle", "children"),
    Input("year-dropdown", "value")
)
def update_regional(year):
    """Regionale Durchschnitte mit Min-Max-Spanne"""
    filtered = df[df["year"] == year]

    regional_stats = (filtered.groupby("region_name")["happiness_score"]
                     .agg(["mean", "min", "max", "count"])
                     .reset_index())
    regional_stats.columns = ["region", "mean", "min", "max", "n"]
    regional_stats = regional_stats.sort_values("mean", ascending=True)

    # Fehlerbalken: Abstand vom Mittelwert zu Min und Max
    regional_stats["error_minus"] = regional_stats["mean"] - regional_stats["min"]
    regional_stats["error_plus"] = regional_stats["max"] - regional_stats["mean"]

    # Globaler Durchschnitt
    global_avg = filtered["happiness_score"].mean()

    # Farben aus der Weltkarten-Farbskala (Rot-Blau basierend auf Score)
    def score_to_color(score):
        norm = (score - 2) / 6
        norm = max(0, min(1, norm))
        if norm <= 0.17:
            return "#67001f"
        elif norm <= 0.33:
            return "#b2182b"
        elif norm <= 0.5:
            return "#d6604d"
        elif norm <= 0.67:
            return "#92c5de"
        elif norm <= 0.83:
            return "#2166ac"
        else:
            return "#053061"

    colors = [score_to_color(m) for m in regional_stats["mean"]]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=regional_stats["mean"],
        y=regional_stats["region"],
        orientation="h",
        marker_color=colors,
        error_x=dict(
            type="data",
            array=regional_stats["error_plus"],
            arrayminus=regional_stats["error_minus"],
            color="#666666",
            thickness=1.5,
            width=4
        ),
        customdata=np.column_stack([regional_stats["n"], regional_stats["min"], regional_stats["max"]]),
        hovertemplate="<b>%{y}</b><br>Ø %{x:.2f}<br>Min: %{customdata[1]:.2f} · Max: %{customdata[2]:.2f}<br>n=%{customdata[0]}<extra></extra>"
    ))

    # Globaler Durchschnitt als Referenz
    fig.add_vline(
        x=global_avg,
        line_dash="dot",
        line_color="#333333",
        line_width=1,
        annotation_text=f"Ø {global_avg:.2f}",
        annotation_position="top",
        annotation_font_size=9
    )

    fig.update_layout(
        **{k: v for k, v in LAYOUT_BASE.items() if k not in ["margin", "hoverlabel"]},
        margin={"l": 180, "r": 16, "t": 24, "b": 40},
        xaxis_title="Happiness Score",
        xaxis_range=[0, 8],
        yaxis_title="",
        showlegend=False,
        hoverlabel=dict(
            bgcolor="white",
            font_size=12,
            font_family="Inter, sans-serif",
            font_color="#1a1a1a",
            bordercolor="#e0e0e0"
        )
    )

    return fig, f"{year}"


# ============================================================================
# Server starten
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  WORLD HAPPINESS REPORT DASHBOARD")
    print("=" * 50)
    print(f"  Datensätze:     {len(df):,}")
    print(f"  Zeitraum:       {min(YEARS)} – {max(YEARS)}")
    print(f"  Regionen:       {len(REGIONS)}")
    print(f"  Faktordaten:    bis {LATEST_FACTOR_YEAR}")
    print(f"  SciPy:          {'verfügbar' if SCIPY_AVAILABLE else 'Fallback'}")
    print("=" * 50)
    print("  Server: http://localhost:8050")
    print("=" * 50 + "\n")

    app.run(debug=True, host="0.0.0.0", port=8050)
