"""
Schema-Drift-Wächter.

Wird VOR jedem Jahres-Refresh ausgeführt. Prüft, dass die neue CSV genau
die erwarteten Spalten in der erwarteten Reihenfolge hat. Wenn nicht,
bricht das Skript mit Diff ab — die Pipeline läuft dann erst gar nicht.

Gegenmaßnahme zu F1 (Schema-Drift). Ergänzt durch F2 (Mindest-Befüllung
der Faktorspalten ab 2019) und F6/F7 (Lückenliste protokollieren).

Aufruf:
    python3 scripts/validate_schema.py data/world_happiness_data_2026.csv
Exit-Code 0 = grün, !=0 = rot, Pipeline stoppt.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

# Vertrag — wird hier ZENTRAL gepflegt, sonst nirgends.
EXPECTED_COLUMNS: list[str] = [
    "Year",
    "Rank",
    "Country name",
    "Life evaluation (3-year average)",
    "Lower whisker",
    "Upper whisker",
    "Explained by: Log GDP per capita",
    "Explained by: Social support",
    "Explained by: Healthy life expectancy",
    "Explained by: Freedom to make life choices",
    "Explained by: Generosity",
    "Explained by: Perceptions of corruption",
    "Dystopia + residual",
    "source_url",
]

FACTOR_COLS = [c for c in EXPECTED_COLUMNS if c.startswith("Explained by:")]

# Erwartete Wertebereiche (Sanity-Checks, keine Statistik)
RANGE_CHECKS = {
    "Life evaluation (3-year average)": (0.0, 10.0),
    "Rank":                              (1,    250),
}

class SchemaDriftError(RuntimeError):
    pass

def check_columns(df: pd.DataFrame) -> None:
    got = list(df.columns)
    if got != EXPECTED_COLUMNS:
        missing = [c for c in EXPECTED_COLUMNS if c not in got]
        extra   = [c for c in got if c not in EXPECTED_COLUMNS]
        reordered = (
            sorted(got) == sorted(EXPECTED_COLUMNS) and got != EXPECTED_COLUMNS
        )
        msg = ["SCHEMA-DRIFT erkannt:"]
        if missing:   msg.append(f"  fehlende Spalten:  {missing}")
        if extra:     msg.append(f"  zusaetzliche:      {extra}")
        if reordered: msg.append(f"  Reihenfolge geaendert (Pipeline ist positionsabhaengig)")
        raise SchemaDriftError("\n".join(msg))

def check_grain_unique(df: pd.DataFrame) -> None:
    dup = df.duplicated(subset=["Year", "Country name"], keep=False)
    if dup.any():
        raise SchemaDriftError(
            f"Grain (Year, Country name) nicht eindeutig: {dup.sum()} Duplikate."
        )

def check_ranges(df: pd.DataFrame) -> None:
    for col, (lo, hi) in RANGE_CHECKS.items():
        s = pd.to_numeric(df[col], errors="coerce")
        out = s[(s < lo) | (s > hi)]
        if not out.empty:
            raise SchemaDriftError(
                f"Wertebereich verletzt in {col!r}: "
                f"{len(out)} Zeilen ausserhalb [{lo}, {hi}]."
            )

def report_data_quality(df: pd.DataFrame) -> None:
    """Kein Fehler, nur Protokoll. Sichtbar machen, was man sonst übersieht."""
    print("\n--- Datenqualitäts-Report (informativ) ---")
    print(f"  Zeilen gesamt:         {len(df)}")
    print(f"  Jahre vorhanden:       "
          f"{sorted(df['Year'].astype(int).unique())}")
    print(f"  Distinct Länder:       {df['Country name'].nunique()}")

    # F2: Faktor-Befüllung pro Jahr
    print("\n  Faktor-Befüllung pro Jahr (F2):")
    for y, g in df.groupby("Year"):
        filled = g[FACTOR_COLS[0]].notna().mean() * 100
        flag = "✓" if filled > 50 else "⚠ nur ranking/score nutzbar"
        print(f"    {int(y)}: {filled:5.1f}%   {flag}")

    # F6/F7: Land × Jahr-Lücken
    all_years = sorted(df["Year"].astype(int).unique())
    gaps = []
    for c, g in df.groupby("Country name"):
        yrs = set(g["Year"].astype(int))
        missing = [y for y in all_years if y not in yrs]
        if missing:
            gaps.append((c, missing))
    if gaps:
        print(f"\n  Zeitreihen-Lücken (F6/F7): {len(gaps)} Länder betroffen.")
        for c, m in sorted(gaps, key=lambda x: -len(x[1]))[:5]:
            print(f"    {c!r}: fehlt {m}")

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Aufruf: {argv[0]} <pfad-zur-csv>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"Datei nicht gefunden: {path}", file=sys.stderr); return 2

    df = pd.read_csv(path, encoding="utf-8-sig")
    try:
        check_columns(df)
        check_grain_unique(df)
        check_ranges(df)
    except SchemaDriftError as e:
        print(f"\n✗ VERTRAG VERLETZT\n{e}\n", file=sys.stderr)
        return 1

    print(f"✓ Vertrag eingehalten: {path}")
    report_data_quality(df)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
