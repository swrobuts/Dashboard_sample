# Phil Rainforest Data Tool — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Phil answers data-backed Amazon deforestation questions by querying the Rainforest Supabase database via Anthropic tool_use, injecting results as context before the streaming chat response.

**Architecture:** New `backend/rainforest_store.py` handles keyword detection, tool definition, Anthropic tool_use call (Haiku, non-streaming, cheap), and PostgREST execution. `main.py` adds a single block after web search that appends the result to `context_str`. Zero new dependencies.

**Tech Stack:** Anthropic Python SDK (existing), requests (existing), FastAPI (existing), pytest + unittest.mock (existing test stack).

---

## Repo paths

- **Phil webapp:** `Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/`
  (all paths below are relative to this root unless stated otherwise)
- **UC4 webapp:** `Knowledge Navigator Use Cases/UC4_Interaktive_Datenvisualisierung/webapp/`
- **Phil landing page:** `/tmp/phil-website/`

---

## Task 1: Update landing page + docs for Rainforest Dashboard

**Files:**
- Modify: `/tmp/phil-website/index.html:724`
- Modify: `/tmp/phil-website/docs/use-cases.md:17`

No test needed — text change only.

**Step 1: Edit `index.html` line 724**

Find this exact string:
```html
<div class="ct-phil"><strong>Data Visualisation</strong><p>Dashboard tiles show mail category trends and Pareto distributions. WorldHappiness data story demonstrates on-demand charting. Full simulation not implemented.</p></div>
```

Replace with:
```html
<div class="ct-phil"><strong>Data Visualisation</strong><p>Dashboard tiles show mail category trends and Pareto distributions. Live <a href="https://rainforest.butscher.cloud" target="_blank">Rainforest Dashboard</a> demonstrates interactive deforestation data with simulation. Full on-demand chart generation not implemented.</p></div>
```

**Step 2: Edit `docs/use-cases.md` line 17**

Find:
```
| 5 | **Data Visualisation** — interactive charts, geographic simulations | — Not in Phil (see WorldHappiness project) | ChatGPT Code Interpreter, Plotly |
```

Replace with:
```
| 5 | **Data Visualisation** — interactive charts, geographic simulations | Partial — live [Rainforest Dashboard](https://rainforest.butscher.cloud) (deforestation monitor, animated maps, scenario simulation) | ChatGPT Code Interpreter, Plotly |
```

**Step 3: Commit and push phil-website**

```bash
cd /tmp/phil-website
git add index.html docs/use-cases.md
git commit -m "feat(use-cases): add Rainforest Dashboard to UC 05 — live deforestation monitor"
git push
```

Expected: pushed to origin, CI/CD deploys updated site.

---

## Task 2: Commit UC4 dashboard changes

The UC4 `app.py` has uncommitted changes from this session (annotation fix, lesehilfe, KPI title).

**Files:**
- Commit: `UC4_Interaktive_Datenvisualisierung/webapp/app.py`

**Step 1: Check status**

```bash
cd "Knowledge Navigator Use Cases"
git status
```

Expected: `app.py` shows as modified under UC4.

**Step 2: Commit**

```bash
git add "UC4_Interaktive_Datenvisualisierung/webapp/app.py"
git commit -m "$(cat <<'EOF'
feat(UC4): treemap year annotation fix, KPI dynamic title, lesehilfe 3-column

- Treemap year annotation moved inside chart (y=0.06) — eliminates dead space above chart
- margin.t reduced 68→4, buttons now sit flush above treemap content
- KPI 'Loss rate' title now dynamic: 'Verlustrate (Jahresdurchschnitt {year})'
- kpi-tempo-title moved from language callback to KPI callback
- Treemap lesehilfe: 3-column structure (What/Key message/Background) in DE+EN

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Supabase credentials to Phil's environment

Phil's `.env` does not yet have `SUPABASE_URL` / `SUPABASE_KEY`. These are needed for `rainforest_store.py`.

**Files:**
- Modify: `backend/.env` (or root `.env` — wherever Phil loads env vars from)

**Step 1: Find Phil's .env**

```bash
ls Knowledge\ Navigator\ Use\ Cases/UC2_Nachrichten_Triage/webapp/
```

Look for `.env` at the webapp root.

**Step 2: Add the two keys**

Append to `.env` (do NOT overwrite existing keys):
```
SUPABASE_URL=https://supabase.butscher.cloud
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiYXNlIiwiaWF0IjoxNzYyNjc5NTM1LCJleHAiOjIwNzgwMzk1MzV9.Fv3soDCs_GrM9MA-4Goq1ANCoJ7KzVpuJ9l9z7bQEwk
```

(Same values as `UC4_Interaktive_Datenvisualisierung/webapp/.env`.)

**Step 3: Verify .env is in .gitignore**

```bash
grep ".env" Knowledge\ Navigator\ Use\ Cases/UC2_Nachrichten_Triage/webapp/.gitignore
```

Expected: `.env` is listed. If not, add it.

---

## Task 4: Create `backend/rainforest_store.py`

**Files:**
- Create: `backend/rainforest_store.py`
- Test: `tests/test_rainforest_store.py`

### Step 1: Write the failing tests first

Create `tests/test_rainforest_store.py`:

```python
# tests/test_rainforest_store.py
"""Tests for rainforest_store — keyword detection, tool definition, HTTP execution."""
import json
from unittest.mock import MagicMock, patch

import pytest


# ── keyword detection ────────────────────────────────────────────────────────

def test_is_rainforest_query_true_german():
    from backend.rainforest_store import is_rainforest_query
    assert is_rainforest_query("Welche Entwaldung gab es 2022?") is True

def test_is_rainforest_query_true_english():
    from backend.rainforest_store import is_rainforest_query
    assert is_rainforest_query("Which state had the most deforestation?") is True

def test_is_rainforest_query_true_amazon():
    from backend.rainforest_store import is_rainforest_query
    assert is_rainforest_query("Wie steht es um den Amazonas?") is True

def test_is_rainforest_query_false_unrelated():
    from backend.rainforest_store import is_rainforest_query
    assert is_rainforest_query("Was steht in meinen Emails heute?") is False

def test_is_rainforest_query_false_calendar():
    from backend.rainforest_store import is_rainforest_query
    assert is_rainforest_query("Wann ist mein nächstes Meeting?") is False


# ── tool definition structure ────────────────────────────────────────────────

def test_tool_definition_has_required_fields():
    from backend.rainforest_store import RAINFOREST_TOOL
    assert RAINFOREST_TOOL["name"] == "query_rainforest_data"
    assert "description" in RAINFOREST_TOOL
    schema = RAINFOREST_TOOL["input_schema"]
    assert schema["type"] == "object"
    assert "endpoint" in schema["properties"]
    assert "endpoint" in schema["required"]

def test_tool_definition_endpoints():
    from backend.rainforest_store import RAINFOREST_TOOL
    allowed = set(RAINFOREST_TOOL["input_schema"]["properties"]["endpoint"]["enum"])
    assert "fact_deforestation" in allowed
    assert "v_deforestation_socio" in allowed
    assert "dim_state" in allowed


# ── execute_rainforest_query ──────────────────────────────────────────────────

def test_execute_query_basic(monkeypatch):
    """Verify correct URL, headers, and params are built for a simple query."""
    from backend.rainforest_store import execute_rainforest_query

    fake_rows = [{"year": 2022, "state_code": "PA", "deforestation_km2": 1776}]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_rows
    mock_resp.raise_for_status = MagicMock()

    with patch("backend.rainforest_store.requests.get", return_value=mock_resp) as mock_get:
        result = execute_rainforest_query({
            "endpoint": "v_deforestation_socio",
            "filters": {"year": "eq.2022"},
            "order": "deforestation_km2.desc",
            "limit": 5,
        })

    call_kwargs = mock_get.call_args
    url = call_kwargs[0][0]
    headers = call_kwargs[1]["headers"]
    params = call_kwargs[1]["params"]

    assert "v_deforestation_socio" in url
    assert headers["Accept-Profile"] == "Rainforest"
    assert params["year"] == "eq.2022"
    assert params["order"] == "deforestation_km2.desc"
    assert params["limit"] == 5
    assert "PA" in result
    assert "1776" in result

def test_execute_query_no_results(monkeypatch):
    from backend.rainforest_store import execute_rainforest_query

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()

    with patch("backend.rainforest_store.requests.get", return_value=mock_resp):
        result = execute_rainforest_query({"endpoint": "dim_state"})

    assert "keine Daten" in result.lower() or "no data" in result.lower() or result == ""

def test_execute_query_http_error(monkeypatch):
    from backend.rainforest_store import execute_rainforest_query
    import requests as req_lib

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = req_lib.HTTPError("404")

    with patch("backend.rainforest_store.requests.get", return_value=mock_resp):
        result = execute_rainforest_query({"endpoint": "fact_deforestation"})

    assert result == "" or "fehler" in result.lower() or "error" in result.lower()


# ── fetch_rainforest_with_tool ───────────────────────────────────────────────

def test_fetch_rainforest_no_tool_use(monkeypatch):
    """If Claude doesn't call the tool, return None."""
    from backend.rainforest_store import fetch_rainforest_with_tool

    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = []

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("backend.rainforest_store.anthropic.Anthropic", return_value=mock_client):
        result = fetch_rainforest_with_tool("Wie spät ist es?")

    assert result is None

def test_fetch_rainforest_with_tool_use(monkeypatch):
    """If Claude calls the tool, execute query and return context block."""
    from backend.rainforest_store import fetch_rainforest_with_tool

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"endpoint": "v_deforestation_socio", "filters": {"year": "eq.2022"}, "order": "deforestation_km2.desc", "limit": 3}

    mock_response = MagicMock()
    mock_response.stop_reason = "tool_use"
    mock_response.content = [tool_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    fake_rows = [{"year": 2022, "state_code": "PA", "deforestation_km2": 1776}]
    mock_http = MagicMock()
    mock_http.status_code = 200
    mock_http.json.return_value = fake_rows
    mock_http.raise_for_status = MagicMock()

    with patch("backend.rainforest_store.anthropic.Anthropic", return_value=mock_client):
        with patch("backend.rainforest_store.requests.get", return_value=mock_http):
            result = fetch_rainforest_with_tool("Welcher Staat hatte 2022 die höchste Entwaldung?")

    assert result is not None
    assert "Rainforest" in result or "deforestation" in result.lower() or "PA" in result
```

**Step 2: Run tests — verify all FAIL**

```bash
cd "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp"
python -m pytest tests/test_rainforest_store.py -v 2>&1 | head -40
```

Expected: `ModuleNotFoundError: No module named 'backend.rainforest_store'` — that's correct.

**Step 3: Implement `backend/rainforest_store.py`**

```python
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
            max_tokens=300,
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
```

**Step 4: Run tests — all should pass**

```bash
python -m pytest tests/test_rainforest_store.py -v
```

Expected: all 11 tests PASS.

**Step 5: Commit**

```bash
git add backend/rainforest_store.py tests/test_rainforest_store.py
git commit -m "feat(rainforest): rainforest_store.py — tool_use query against Supabase

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Wire rainforest tool into Phil's chat endpoint

**Files:**
- Modify: `backend/main.py` — add import + single context block after web search

**Step 1: Write the failing test**

Add to `tests/test_rainforest_store.py` (or a new `tests/test_chat_rainforest.py`):

```python
# tests/test_chat_rainforest.py
"""Integration smoke test: rainforest context is injected when keywords detected."""
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def test_chat_injects_rainforest_context_on_keyword(monkeypatch):
    """When message contains 'deforestation', fetch_rainforest_with_tool is called."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    from backend.main import app
    client = TestClient(app)

    with patch("backend.main.fetch_rainforest_with_tool") as mock_rf:
        mock_rf.return_value = "\n\n## Rainforest Database Query Result\n```json\n[]\n```\n"
        with patch("backend.main._get_llm") as mock_llm:
            mock_llm.return_value.stream.return_value = iter(["test response"])
            resp = client.post(
                "/api/chat",
                json={"message": "Welcher Staat hatte die höchste Entwaldung 2022?",
                      "include_context": False},
            )

    mock_rf.assert_called_once()
    assert resp.status_code == 200


def test_chat_skips_rainforest_on_unrelated_message(monkeypatch):
    """When message is about email, fetch_rainforest_with_tool is NOT called."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from backend.main import app
    client = TestClient(app)

    with patch("backend.main.fetch_rainforest_with_tool") as mock_rf:
        with patch("backend.main._get_llm") as mock_llm:
            mock_llm.return_value.stream.return_value = iter(["test response"])
            client.post(
                "/api/chat",
                json={"message": "Was steht in meinen Emails?", "include_context": False},
            )

    mock_rf.assert_not_called()
```

**Step 2: Run tests — verify they FAIL**

```bash
python -m pytest tests/test_chat_rainforest.py -v 2>&1 | head -20
```

Expected: `ImportError` or `AssertionError` — `fetch_rainforest_with_tool` not yet wired into `main.py`.

**Step 3: Add import to `main.py`**

Find the import section at the top of `backend/main.py` where other stores are imported. Near the lines that import `web_search`, add:

```python
from backend.rainforest_store import fetch_rainforest_with_tool, is_rainforest_query
```

**Step 4: Add rainforest block to chat endpoint**

In `backend/main.py`, find this block (around line 1106–1122):

```python
    # Web search: trigger on keywords in user message
    if WEB_SEARCH_TRIGGER_RE.search(req.message):
        try:
            web_str, web_results = build_web_context(req.message)
            ...
        except Exception as exc:
            logging.warning(f"[Memory] Web-Suche fehlgeschlagen: {exc}")
```

Immediately **after** that block (before `user_msg = ...`), add:

```python
    # Rainforest: tool_use query for deforestation data
    if is_rainforest_query(req.message):
        try:
            rf_str = fetch_rainforest_with_tool(req.message)
            if rf_str:
                context_str += rf_str
        except Exception as exc:
            logging.warning(f"[Rainforest] Tool query fehlgeschlagen: {exc}")
```

**Step 5: Run tests — all should pass**

```bash
python -m pytest tests/test_rainforest_store.py tests/test_chat_rainforest.py -v
```

Expected: all tests PASS.

**Step 6: Run full test suite — no regressions**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all existing tests still pass.

**Step 7: Commit**

```bash
git add backend/main.py tests/test_chat_rainforest.py
git commit -m "feat(chat): inject Rainforest data context via tool_use on deforestation queries

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Smoke test via Phil UI

**No code changes — verification only.**

**Step 1: Start Phil locally**

```bash
cd "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp"
docker-compose -f docker-compose.local.yml up -d
```

Or if running the backend directly:
```bash
uvicorn backend.main:app --reload --port 8000
```

**Step 2: Send a deforestation question via curl**

```bash
curl -s -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Welcher Bundesstaat hatte 2022 die höchste Entwaldung?", "include_context": false}' \
  | head -50
```

Expected output (SSE stream):
- Some chunks containing a Brazilian state name (e.g. "Pará" or "PA")
- A number (km² value)
- `data: [DONE]` at end

**Step 3: Verify normal messages still work**

```bash
curl -s -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Guten Morgen Phil", "include_context": false}' \
  | head -20
```

Expected: normal greeting response, no rainforest data injected.

**Step 4: Check logs for tool call**

```bash
docker logs <phil_container_name> 2>&1 | grep -i rainforest | tail -10
```

Expected: `[Rainforest] Tool query` log entry for the deforestation question, nothing for the greeting.
