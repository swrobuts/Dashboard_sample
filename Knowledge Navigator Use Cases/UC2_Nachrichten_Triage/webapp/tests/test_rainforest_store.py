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
