# backend/rainforest_store.py
"""
Rainforest data tool for Phil.

When the user's message contains deforestation/Amazon keywords, this module:
1. Calls Claude (Haiku, non-streaming) with a query_rainforest_data tool
2. Claude returns structured query parameters
3. We execute a read-only PostgREST call against supabase.butscher.cloud
4. Result is returned as a context block string for injection into Phil's chat context

Zero new dependencies — uses anthropic (already in requirements) and requests (already in requirements).
"""
from __future__ import annotations

import json
import logging
import os

import anthropic
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://supabase.butscher.cloud")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SCHEMA = "Rainforest"

# ── Keyword detection ─────────────────────────────────────────────────────────

RAINFOREST_KEYWORDS = {
    "regenwald", "rainforest", "amazon", "amazonas", "entwaldung",
    "deforestation", "desmatamento", "inpe", "prodes", "floresta",
    "wald", "forest", "abholzung", "rodung", "deforest",
}


def is_rainforest_query(message: str) -> bool:
    """Return True if the message likely asks about Amazon deforestation data."""
    lower = message.lower()
    return any(kw in lower for kw in RAINFOREST_KEYWORDS)


# ── Tool definition ───────────────────────────────────────────────────────────

RAINFOREST_TOOL: dict = {
    "name": "query_rainforest_data",
    "description": (
        "Query Amazon deforestation data from the Rainforest database. "
        "Use for questions about deforestation rates, state rankings, annual trends, "
        "state comparisons, or socioeconomic correlations. "
        "Data: Brazilian Amazon states, years 2010–2024, source INPE PRODES."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "endpoint": {
                "type": "string",
                "enum": ["fact_deforestation", "v_deforestation_socio", "dim_state"],
                "description": (
                    "fact_deforestation: raw annual area by state+class. "
                    "v_deforestation_socio: aggregated per-state with GDP/population/intensity. "
                    "dim_state: state metadata (total area, Amazon area, region)."
                ),
            },
            "filters": {
                "type": "object",
                "description": (
                    "PostgREST filter params. Keys = column names, values = PostgREST operators. "
                    "Examples: {'year': 'eq.2022'}, {'state_code': 'eq.PA'}, "
                    "{'deforestation_km2': 'gt.500'}. Omit for all rows."
                ),
            },
            "order": {
                "type": "string",
                "description": "Order clause e.g. 'deforestation_km2.desc' or 'year.asc'. Optional.",
            },
            "limit": {
                "type": "integer",
                "description": "Max rows to return. Default 10, max 50.",
                "default": 10,
            },
        },
        "required": ["endpoint"],
    },
}

_TOOL_SYSTEM = (
    "You are a data routing assistant. "
    "If the user message asks about Amazon deforestation, Brazilian states, INPE data, "
    "forest loss, or related topics, use the query_rainforest_data tool to fetch relevant data. "
    "Choose the most specific query: prefer v_deforestation_socio for per-state aggregates, "
    "fact_deforestation for class breakdowns, dim_state for area/region metadata. "
    "If the question is unrelated to deforestation, do NOT call the tool."
)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"


# ── PostgREST execution ───────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept-Profile": SCHEMA,
        "Content-Type": "application/json",
    }


def execute_rainforest_query(tool_input: dict) -> str:
    """
    Execute a PostgREST query based on Claude's tool_use parameters.
    Returns a formatted string suitable for context injection, or "" on error/empty.
    """
    endpoint = tool_input.get("endpoint", "")
    filters = tool_input.get("filters", {}) or {}
    order = tool_input.get("order", "")
    limit = min(int(tool_input.get("limit", 10)), 50)

    params: dict = {**filters}
    if order:
        params["order"] = order
    params["limit"] = limit

    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=10)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:
        logging.warning(f"[Rainforest] PostgREST error: {exc}")
        return ""

    if not rows:
        return ""

    # Format as compact JSON block for context injection
    summary = json.dumps(rows, ensure_ascii=False, indent=None)
    return (
        f"\n\n## Rainforest Database Query Result\n"
        f"Endpoint: {endpoint} | Filters: {filters} | Rows: {len(rows)}\n"
        f"```json\n{summary}\n```\n"
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_rainforest_with_tool(user_message: str) -> str | None:
    """
    Use Claude Haiku with tool_use to decide what to query, execute it,
    and return a context block string.

    Returns None if Claude doesn't call the tool (question unrelated to deforestation).
    Returns "" if tool was called but query returned no data or errored.
    Returns formatted context string on success.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logging.warning("[Rainforest] ANTHROPIC_API_KEY not set — skipping tool query")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=512,
            system=_TOOL_SYSTEM,
            tools=[RAINFOREST_TOOL],
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:
        logging.warning(f"[Rainforest] Claude tool call failed: {exc}")
        return None

    if response.stop_reason != "tool_use":
        return None

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        return None

    return execute_rainforest_query(tool_block.input)
