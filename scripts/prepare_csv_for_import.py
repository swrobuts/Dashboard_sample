"""
Normalize CSV headers to match happiness_raw table columns.

Die WHR-CSV hat menschenlesbare Spaltennamen mit Leerzeichen, Doppelpunkten
und Klammern. Supabase Table Editor's CSV-Import matched Header-Zeilen exakt
gegen Tabellen-Spalten — kein manuelles Mapping möglich.

Dieses Skript schreibt eine Kopie mit snake_case-Headern, die direkt
in happiness_raw geladen werden kann.

Gegenmaßnahme zu F1 (Schema-Drift): wenn WHR im nächsten Release Spalten
umbenennt, schlägt dieses Skript laut fehl — bevor schlechte Daten in
die Tabelle wandern.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC  = ROOT / "data" / "world_happiness_data_2011_2025.csv"
DST  = ROOT / "data" / "world_happiness_2011_2025_import.csv"

HEADER_MAP: dict[str, str] = {
    "Year":                                         "year",
    "Rank":                                         "rank",
    "Country name":                                 "country_name",
    "Life evaluation (3-year average)":             "life_evaluation_3y",
    "Lower whisker":                                "lower_whisker",
    "Upper whisker":                                "upper_whisker",
    "Explained by: Log GDP per capita":             "explained_log_gdp",
    "Explained by: Social support":                 "explained_social_support",
    "Explained by: Healthy life expectancy":        "explained_healthy_life",
    "Explained by: Freedom to make life choices":   "explained_freedom",
    "Explained by: Generosity":                     "explained_generosity",
    "Explained by: Perceptions of corruption":      "explained_corruption",
    "Dystopia + residual":                          "dystopia_residual",
    "source_url":                                   "source_url",
}

def main() -> int:
    df = pd.read_csv(SRC, encoding="utf-8-sig")

    expected = set(HEADER_MAP.keys())
    got      = set(df.columns)
    missing  = expected - got
    extra    = got - expected
    if missing or extra:
        print("CSV-Header weicht vom erwarteten Schema ab:")
        if missing: print(f"  fehlende Spalten:    {sorted(missing)}")
        if extra:   print(f"  zusätzliche Spalten: {sorted(extra)}")
        return 1

    df = df.rename(columns=HEADER_MAP)
    df.to_csv(DST, index=False, encoding="utf-8")
    print(f"OK: {len(df)} Zeilen geschrieben → {DST}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())