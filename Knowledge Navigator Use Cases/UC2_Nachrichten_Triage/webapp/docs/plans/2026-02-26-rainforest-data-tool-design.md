# Rainforest Data Tool for Phil — Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Phil can answer data-backed questions about Amazon deforestation by querying the Rainforest Supabase database via Anthropic tool_use.

**Architecture:** One new file (`rainforest_store.py`) defines the tool and executes PostgREST calls. `main.py` chat endpoint gets a keyword-triggered tool loop. Zero new dependencies — same Supabase PostgREST pattern as UC4 `data_loader.py`.

**Tech Stack:** Anthropic tool_use (existing), PostgREST HTTP (existing pattern), FastAPI (existing).

---

## Context

The Rainforest Supabase lives at `https://supabase.butscher.cloud`, schema `Rainforest`.
Key tables/views:
- `fact_deforestation` — year, state_id, class_id, area_km2, accumulated_km2
- `v_deforestation_socio` — year, state_code, deforestation_km2, accumulated_km2, gdp_per_capita_brl, population, defor_per_1000km2, defor_per_100k_pop
- `dim_state` — state_id, state_name, state_code, region, area_total_km2, area_amazonia_km2

Credentials: `SUPABASE_URL` and `SUPABASE_KEY` in `.env` (same keys already in UC4).

Phil's chat endpoint is at `backend/main.py:1056`. It currently builds context (RAG, calendar, mail) and calls Claude without tools. No tool_use exists anywhere in Phil today.

---

## Design Decisions

**Why keyword-triggered, not always-on:** Offering tools to Claude on every request adds latency and cost. Deforestation questions are a specific domain — activating the tool only when relevant keywords appear keeps normal conversation fast.

**Why three fixed endpoints, not free-form SQL:** PostgREST filters are safe by design (read-only GET, no injection risk). Restricting Claude to known endpoints prevents hallucinated table names.

**Why a single tool with `endpoint` + `filters`:** One flexible tool is simpler than three separate tools. Claude handles the parameter selection; the execution layer just passes them through.

---

## Housekeeping tasks (before the feature)

### Task 1: Update landing page and docs for UC4

**Files:**
- Modify: `/tmp/phil-website/index.html` — UC 05 ct-phil text
- Modify: `/tmp/phil-website/docs/use-cases.md` — UC 5 row

**Change:** Replace "WorldHappiness data story demonstrates on-demand charting. Full simulation not implemented." with a mention of the live Rainforest Dashboard at `rainforest.butscher.cloud`.

### Task 2: Commit UC4 changes + push phil-website

- `git add` + `git commit` in the UC4 repo (current `app.py` changes)
- `git add` + `git commit` + `git push` in `/tmp/phil-website`

---

## Feature tasks

### Task 3: `backend/rainforest_store.py`

New file. Contains:

```python
RAINFOREST_TOOL = {
    "name": "query_rainforest_data",
    "description": (
        "Query Amazon deforestation data from the Rainforest database. "
        "Use this for any question about deforestation rates, rankings, trends, "
        "state comparisons, or socioeconomic correlations. "
        "Data covers Brazilian Amazon states, years 2010–2024, source: INPE PRODES."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "endpoint": {
                "type": "string",
                "enum": ["fact_deforestation", "v_deforestation_socio", "dim_state"],
                "description": "fact_deforestation: raw annual area by state+class. v_deforestation_socio: aggregated per-state with GDP/population. dim_state: state metadata (area, region)."
            },
            "filters": {
                "type": "object",
                "description": "PostgREST filter params. Keys are column names, values are PostgREST operators e.g. {'year': 'eq.2022', 'state_code': 'eq.PA', 'area_km2': 'gt.1000'}. Omit for all rows."
            },
            "order": {
                "type": "string",
                "description": "Order clause e.g. 'area_km2.desc' or 'year.asc'. Optional."
            },
            "limit": {
                "type": "integer",
                "description": "Max rows to return. Default 20, max 100.",
                "default": 20
            }
        },
        "required": ["endpoint"]
    }
}

RAINFOREST_KEYWORDS = {
    "regenwald", "rainforest", "amazon", "amazonas", "entwaldung",
    "deforestation", "desmatamento", "inpe", "prodes", "floresta",
    "wald", "forest", "abholzung", "rodung", "deforest",
}

def is_rainforest_query(message: str) -> bool:
    lower = message.lower()
    return any(kw in lower for kw in RAINFOREST_KEYWORDS)

def execute_rainforest_query(tool_input: dict) -> str:
    # PostgREST GET call, returns JSON string or error message
    ...
```

### Task 4: Modify `main.py` chat endpoint

Add tool loop inside `def chat(...)`:
- Call `is_rainforest_query(req.message)` → if True, pass `tools=[RAINFOREST_TOOL]`
- If response `stop_reason == "tool_use"` → extract tool block → call `execute_rainforest_query` → append `tool_result` → second Claude call for final answer
- Existing flow unchanged if no keyword match

### Task 5: Tests for `rainforest_store.py`

File: `tests/test_rainforest_store.py`

Tests:
- `is_rainforest_query`: True for "Entwaldung", "deforestation 2022", "Amazon Regenwald"; False for "Kalender", "Email"
- `execute_rainforest_query`: mock `requests.get`, verify correct URL + headers + params built
- Tool definition: validates that `RAINFOREST_TOOL["input_schema"]` is valid JSON Schema

### Task 6: Smoke test

- `curl` the local Phil chat endpoint with "Welcher Staat hatte 2022 die höchste Entwaldung?" — verify tool is called and answer contains a state name + number
- Verify normal message "Was steht in meinen Emails?" still works without tool activation
