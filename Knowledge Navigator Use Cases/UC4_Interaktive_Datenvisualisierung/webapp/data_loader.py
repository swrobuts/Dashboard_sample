"""
Rainforest Dashboard — Supabase Data Loader
Connects via PostgREST API with Accept-Profile: Rainforest header.
Pattern identical to the WorldHappiness dashboard data_loader.py.
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
    resp = requests.get(url, headers=_headers(), params=params or {}, timeout=30)
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


@lru_cache(maxsize=1)
def load_states() -> pd.DataFrame:
    return _fetch("dim_state")


@lru_cache(maxsize=1)
def load_classes() -> pd.DataFrame:
    return _fetch("dim_class")


@lru_cache(maxsize=1)
def load_deforestation_data() -> pd.DataFrame:
    facts = _fetch("fact_deforestation", {"order": "year.asc"})
    states = load_states()
    classes = load_classes()
    df = (
        facts
        .merge(states[["state_id", "state_name", "region"]], on="state_id", how="left")
        .merge(classes[["class_id", "class_name"]], on="class_id", how="left")
    )
    df["year"] = df["year"].astype(int)
    df["area_km2"] = df["area_km2"].astype(float)
    df["accumulated_km2"] = df["accumulated_km2"].astype(float)
    return df


def get_years() -> list:
    return sorted(load_deforestation_data()["year"].unique().tolist())


def get_classes() -> list:
    return sorted(load_deforestation_data()["class_name"].dropna().unique().tolist())


def get_states() -> list:
    return sorted(load_deforestation_data()["state_name"].dropna().unique().tolist())


def clear_cache():
    load_states.cache_clear()
    load_classes.cache_clear()
    load_deforestation_data.cache_clear()
