"""
World Happiness Report - Supabase Data Loader
Verbindung zur PostgREST API mit Accept-Profile Header für WorldHappiness Schema
"""

import requests
import pandas as pd
from functools import lru_cache
import os

# Supabase Konfiguration
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://supabase.butscher.cloud")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiYXNlIiwiaWF0IjoxNzYyNjc5NTM1LCJleHAiOjIwNzgwMzk1MzV9.Fv3soDCs_GrM9MA-4Goq1ANCoJ7KzVpuJ9l9z7bQEwk")
SCHEMA = "WorldHappiness"

def get_headers():
    """Standard Headers für Supabase API mit Schema-Auswahl"""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept-Profile": SCHEMA,
        "Content-Type": "application/json"
    }

def fetch_table(table_name: str, params: dict = None) -> pd.DataFrame:
    """Einzelne Tabelle von Supabase laden"""
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return pd.DataFrame(response.json())

@lru_cache(maxsize=1)
def load_regions() -> pd.DataFrame:
    """Alle Regionen laden (gecacht)"""
    return fetch_table("dim_region")

@lru_cache(maxsize=1)
def load_countries() -> pd.DataFrame:
    """Alle Länder mit Region laden (gecacht)"""
    countries = fetch_table("dim_country")
    regions = load_regions()
    return countries.merge(regions, on="region_id", how="left")

@lru_cache(maxsize=1)
def load_happiness_data() -> pd.DataFrame:
    """Komplette Happiness-Daten mit Land und Region laden (gecacht)"""
    # Fakten laden
    facts = fetch_table("fact_happiness", {"order": "year.asc,happiness_rank.asc"})
    
    # Mit Dimensionen joinen
    countries = load_countries()
    
    df = facts.merge(
        countries[["country_id", "country_name", "region_name"]], 
        on="country_id", 
        how="left"
    )
    
    # ISO-3 Codes für Choropleth Map hinzufügen
    df["iso_alpha"] = df["country_name"].map(get_iso_codes())
    
    return df

def get_iso_codes() -> dict:
    """Mapping von Ländernamen zu ISO-3 Codes für Plotly Choropleth"""
    return {
        "Afghanistan": "AFG", "Albania": "ALB", "Algeria": "DZA", "Argentina": "ARG",
        "Armenia": "ARM", "Australia": "AUS", "Austria": "AUT", "Azerbaijan": "AZE",
        "Bahrain": "BHR", "Bangladesh": "BGD", "Belarus": "BLR", "Belgium": "BEL",
        "Benin": "BEN", "Bhutan": "BTN", "Bolivia": "BOL", "Bosnia and Herzegovina": "BIH",
        "Botswana": "BWA", "Brazil": "BRA", "Bulgaria": "BGR", "Burkina Faso": "BFA",
        "Burundi": "BDI", "Cambodia": "KHM", "Cameroon": "CMR", "Canada": "CAN",
        "Central African Republic": "CAF", "Chad": "TCD", "Chile": "CHL", "China": "CHN",
        "Colombia": "COL", "Comoros": "COM", "Congo (Brazzaville)": "COG", 
        "Congo (Kinshasa)": "COD", "Costa Rica": "CRI", "Croatia": "HRV", "Cuba": "CUB",
        "Cyprus": "CYP", "Czech Republic": "CZE", "Denmark": "DNK", "Djibouti": "DJI",
        "Dominican Republic": "DOM", "Ecuador": "ECU", "Egypt": "EGY", "El Salvador": "SLV",
        "Estonia": "EST", "Eswatini": "SWZ", "Ethiopia": "ETH", "Finland": "FIN",
        "France": "FRA", "Gabon": "GAB", "Gambia": "GMB", "Georgia": "GEO",
        "Germany": "DEU", "Ghana": "GHA", "Greece": "GRC", "Guatemala": "GTM",
        "Guinea": "GIN", "Haiti": "HTI", "Honduras": "HND", "Hong Kong": "HKG",
        "Hungary": "HUN", "Iceland": "ISL", "India": "IND", "Indonesia": "IDN",
        "Iran": "IRN", "Iraq": "IRQ", "Ireland": "IRL", "Israel": "ISR",
        "Italy": "ITA", "Ivory Coast": "CIV", "Jamaica": "JAM", "Japan": "JPN",
        "Jordan": "JOR", "Kazakhstan": "KAZ", "Kenya": "KEN", "Kosovo": "XKX",
        "Kuwait": "KWT", "Kyrgyzstan": "KGZ", "Laos": "LAO", "Latvia": "LVA",
        "Lebanon": "LBN", "Lesotho": "LSO", "Liberia": "LBR", "Libya": "LBY",
        "Lithuania": "LTU", "Luxembourg": "LUX", "Macedonia": "MKD", "Madagascar": "MDG",
        "Malawi": "MWI", "Malaysia": "MYS", "Maldives": "MDV", "Mali": "MLI",
        "Malta": "MLT", "Mauritania": "MRT", "Mauritius": "MUS", "Mexico": "MEX",
        "Moldova": "MDA", "Mongolia": "MNG", "Montenegro": "MNE", "Morocco": "MAR",
        "Mozambique": "MOZ", "Myanmar": "MMR", "Namibia": "NAM", "Nepal": "NPL",
        "Netherlands": "NLD", "New Zealand": "NZL", "Nicaragua": "NIC", "Niger": "NER",
        "Nigeria": "NGA", "North Cyprus": "CYP", "Norway": "NOR", "Oman": "OMN",
        "Pakistan": "PAK", "Palestinian Territories": "PSE", "Panama": "PAN",
        "Paraguay": "PRY", "Peru": "PER", "Philippines": "PHL", "Poland": "POL",
        "Portugal": "PRT", "Qatar": "QAT", "Romania": "ROU", "Russia": "RUS",
        "Rwanda": "RWA", "Saudi Arabia": "SAU", "Senegal": "SEN", "Serbia": "SRB",
        "Sierra Leone": "SLE", "Singapore": "SGP", "Slovakia": "SVK", "Slovenia": "SVN",
        "Somalia": "SOM", "South Africa": "ZAF", "South Korea": "KOR", "South Sudan": "SSD",
        "Spain": "ESP", "Sri Lanka": "LKA", "Sudan": "SDN", "Suriname": "SUR",
        "Sweden": "SWE", "Switzerland": "CHE", "Syria": "SYR", "Taiwan": "TWN",
        "Tajikistan": "TJK", "Tanzania": "TZA", "Thailand": "THA", "Togo": "TGO",
        "Trinidad and Tobago": "TTO", "Tunisia": "TUN", "Turkey": "TUR",
        "Turkmenistan": "TKM", "Uganda": "UGA", "Ukraine": "UKR",
        "United Arab Emirates": "ARE", "United Kingdom": "GBR", "United States": "USA",
        "Uruguay": "URY", "Uzbekistan": "UZB", "Venezuela": "VEN", "Vietnam": "VNM",
        "Yemen": "YEM", "Zambia": "ZMB", "Zimbabwe": "ZWE"
    }

def get_available_years() -> list:
    """Verfügbare Jahre aus den Daten"""
    df = load_happiness_data()
    return sorted(df["year"].unique().tolist())

def get_available_regions() -> list:
    """Verfügbare Regionen aus den Daten"""
    regions = load_regions()
    return sorted(regions["region_name"].unique().tolist())

def clear_cache():
    """Cache leeren für Daten-Refresh"""
    load_regions.cache_clear()
    load_countries.cache_clear()
    load_happiness_data.cache_clear()


if __name__ == "__main__":
    # Test der Verbindung
    print("Lade Daten von Supabase...")
    df = load_happiness_data()
    print(f"✓ {len(df)} Datensätze geladen")
    print(f"✓ Jahre: {get_available_years()}")
    print(f"✓ Regionen: {len(get_available_regions())}")
    print(f"\nBeispiel:\n{df.head()}")
