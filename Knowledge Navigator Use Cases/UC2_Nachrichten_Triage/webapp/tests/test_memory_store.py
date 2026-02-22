# tests/test_memory_store.py
import sqlite3
import pytest
from backend.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    """SQLite-only store — ChromaDB skipped for unit tests."""
    s = MemoryStore.__new__(MemoryStore)
    s._db_path = str(tmp_path / "memory.db")
    s._conn = sqlite3.connect(s._db_path, check_same_thread=False)
    s._conn.execute("PRAGMA journal_mode=WAL")
    s._conn.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id              TEXT PRIMARY KEY,
            text            TEXT NOT NULL,
            category        TEXT NOT NULL,
            source          TEXT NOT NULL,
            source_ref      TEXT,
            confidence      REAL DEFAULT 0.7,
            positive_votes  INTEGER DEFAULT 0,
            negative_votes  INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL,
            corrected_at    TEXT,
            correction_note TEXT
        )
    """)
    s._conn.commit()
    s._chroma_collection = None
    return s


def test_upsert_and_list(store):
    store.upsert_fact("f1", "Flaschenpost = Getränkelieferdienst", "Konzept", "chat")
    facts = store.list_facts()
    assert len(facts) == 1
    assert facts[0]["text"] == "Flaschenpost = Getränkelieferdienst"
    assert facts[0]["category"] == "Konzept"
    assert facts[0]["confidence"] == pytest.approx(0.7)


def test_upsert_idempotent(store):
    store.upsert_fact("f1", "Text A", "Konzept", "chat")
    store.upsert_fact("f1", "Text A updated", "Konzept", "chat")
    assert len(store.list_facts()) == 1
    assert store.list_facts()[0]["text"] == "Text A updated"


def test_apply_feedback_up(store):
    store.upsert_fact("f1", "Text", "Konzept", "chat", confidence=0.7)
    store.apply_feedback("f1", "up")
    fact = store.list_facts()[0]
    assert fact["positive_votes"] == 1
    assert fact["confidence"] == pytest.approx(0.75)


def test_apply_feedback_down(store):
    store.upsert_fact("f1", "Text", "Konzept", "chat", confidence=0.7)
    store.apply_feedback("f1", "down")
    fact = store.list_facts()[0]
    assert fact["negative_votes"] == 1
    assert fact["confidence"] == pytest.approx(0.60)


def test_confidence_clamped_at_minimum(store):
    store.upsert_fact("f1", "Text", "Konzept", "chat", confidence=0.2)
    store.apply_feedback("f1", "down")
    store.apply_feedback("f1", "down")
    assert store.list_facts()[0]["confidence"] == pytest.approx(0.10)


def test_delete_fact(store):
    store.upsert_fact("f1", "Text", "Konzept", "chat")
    store.delete_fact("f1")
    assert store.list_facts() == []


def test_update_fact_text(store):
    store.upsert_fact("f1", "Wrong text", "Konzept", "chat")
    store.update_fact("f1", text="Correct text", correction_note="User corrected")
    fact = store.list_facts()[0]
    assert fact["text"] == "Correct text"
    assert fact["correction_note"] == "User corrected"
    assert fact["corrected_at"] is not None


def test_get_fact_returns_dict(store):
    store.upsert_fact("f1", "Flaschenpost = Getränkelieferdienst", "Konzept", "chat")
    fact = store.get_fact("f1")
    assert fact is not None
    assert fact["id"] == "f1"
    assert fact["text"] == "Flaschenpost = Getränkelieferdienst"
    assert fact["category"] == "Konzept"


def test_get_fact_returns_none_for_unknown_id(store):
    result = store.get_fact("does-not-exist")
    assert result is None


def test_list_facts_filter_by_category(store):
    store.upsert_fact("f1", "Max Müller", "Person", "chat")
    store.upsert_fact("f2", "Flaschenpost", "Konzept", "chat")
    assert len(store.list_facts(category="Person")) == 1


def test_list_facts_filter_by_min_confidence(store):
    store.upsert_fact("f1", "High", "Konzept", "chat", confidence=0.8)
    store.upsert_fact("f2", "Low", "Konzept", "chat", confidence=0.2)
    assert len(store.list_facts(min_confidence=0.5)) == 1


def test_stats(store):
    store.upsert_fact("f1", "A", "Person", "chat", confidence=0.8)
    store.upsert_fact("f2", "B", "Konzept", "chat", confidence=0.5)
    stats = store.stats()
    assert stats["total"] == 2
    assert any(s["category"] == "Person" and s["count"] == 1 for s in stats["by_category"])


def test_search_facts_fallback(store):
    """With no ChromaDB, search_facts falls back to SQL ordered by confidence."""
    store.upsert_fact("f1", "High conf", "Konzept", "chat", confidence=0.8)
    store.upsert_fact("f2", "Low conf", "Konzept", "chat", confidence=0.2)
    results = store.search_facts("anything", n_results=5)
    # Only f1 is above _INJECT_THRESHOLD (0.30)
    assert len(results) == 1
    assert results[0]["id"] == "f1"


def test_build_context_block_empty(store):
    assert store.build_context_block("anything") == ""


def test_build_context_block_with_facts(store):
    store.upsert_fact("f1", "Max = Kooperationspartner", "Person", "chat", confidence=0.8)
    block = store.build_context_block("Max")
    assert "PHIL'S GEDÄCHTNIS" in block
    assert "Max = Kooperationspartner" in block
    assert "80%" in block


def test_list_facts_filter_by_source_ref(store):
    store.upsert_fact("f1", "Text A", "Konzept", "chat", source_ref="msg-abc")
    store.upsert_fact("f2", "Text B", "Konzept", "chat", source_ref="msg-xyz")
    result = store.list_facts(source_ref="msg-abc")
    assert len(result) == 1
    assert result[0]["id"] == "f1"


def test_apply_feedback_invalid_rating(store):
    store.upsert_fact("f1", "Text", "Konzept", "chat", confidence=0.7)
    with pytest.raises(ValueError):
        store.apply_feedback("f1", "sideways")


def test_confidence_clamped_at_maximum(store):
    store.upsert_fact("f1", "Text", "Konzept", "chat", confidence=0.98)
    store.apply_feedback("f1", "up")
    store.apply_feedback("f1", "up")
    assert store.list_facts()[0]["confidence"] == pytest.approx(1.0)


# ── WebSearch tests ──────────────────────────────────────────────────────────

import httpx
import respx
from backend.web_search import search_web, build_web_context, WEB_SEARCH_TRIGGER_RE


def test_web_search_trigger_regex_matches():
    assert WEB_SEARCH_TRIGGER_RE.search("Recherchiere mal Flaschenpost")
    assert WEB_SEARCH_TRIGGER_RE.search("was ist Flaschenpost?")
    assert WEB_SEARCH_TRIGGER_RE.search("Wer ist Max Müller")
    assert WEB_SEARCH_TRIGGER_RE.search("was bedeutet ECTS")
    assert WEB_SEARCH_TRIGGER_RE.search("suche mal nach dem Anbieter")


def test_web_search_trigger_regex_no_match():
    assert not WEB_SEARCH_TRIGGER_RE.search("Zeige mir den Kalender")
    assert not WEB_SEARCH_TRIGGER_RE.search("Erstelle eine Aufgabe")
    assert not WEB_SEARCH_TRIGGER_RE.search("Zusammenfassen")


@respx.mock
def test_search_web_returns_snippets():
    respx.get("https://api.duckduckgo.com/").mock(
        return_value=httpx.Response(200, json={
            "Abstract": "Flaschenpost ist ein Getränkelieferdienst.",
            "AbstractURL": "https://example.com",
            "RelatedTopics": [
                {"Text": "Gegründet 2016 in Deutschland", "FirstURL": "https://example.com/2"},
                {"Text": "Liefert Getränkekisten direkt nach Hause", "FirstURL": "https://example.com/3"},
            ],
        })
    )
    results = search_web("Flaschenpost")
    assert len(results) == 3
    assert results[0]["snippet"] == "Flaschenpost ist ein Getränkelieferdienst."
    assert results[0]["url"] == "https://example.com"
    assert results[1]["snippet"] == "Gegründet 2016 in Deutschland"


@respx.mock
def test_search_web_returns_empty_on_no_abstract():
    respx.get("https://api.duckduckgo.com/").mock(
        return_value=httpx.Response(200, json={
            "Abstract": "",
            "AbstractURL": "",
            "RelatedTopics": [],
        })
    )
    results = search_web("xyzzy123notaword")
    assert results == []


@respx.mock
def test_search_web_returns_empty_on_http_error():
    respx.get("https://api.duckduckgo.com/").mock(
        return_value=httpx.Response(500)
    )
    results = search_web("anything")
    assert results == []


@respx.mock
def test_build_web_context_returns_block_and_results():
    respx.get("https://api.duckduckgo.com/").mock(
        return_value=httpx.Response(200, json={
            "Abstract": "Flaschenpost ist ein Getränkelieferdienst.",
            "AbstractURL": "https://example.com",
            "RelatedTopics": [],
        })
    )
    block, results = build_web_context("Flaschenpost")
    assert "WEBSUCHE" in block
    assert "Flaschenpost" in block
    assert len(results) == 1


@respx.mock
def test_build_web_context_empty_on_no_results():
    respx.get("https://api.duckduckgo.com/").mock(
        return_value=httpx.Response(200, json={"Abstract": "", "RelatedTopics": []})
    )
    block, results = build_web_context("nothing")
    assert block == ""
    assert results == []


@respx.mock
def test_search_web_max_results_cap():
    respx.get("https://api.duckduckgo.com/").mock(
        return_value=httpx.Response(200, json={
            "Abstract": "Abstract text",
            "AbstractURL": "https://example.com",
            "RelatedTopics": [
                {"Text": "Topic 1", "FirstURL": "https://example.com/1"},
                {"Text": "Topic 2", "FirstURL": "https://example.com/2"},
                {"Text": "Topic 3", "FirstURL": "https://example.com/3"},
            ],
        })
    )
    results = search_web("test", max_results=2)
    assert len(results) == 2
    assert results[0]["snippet"] == "Abstract text"
    assert results[1]["snippet"] == "Topic 1"


@respx.mock
def test_search_web_max_results_one_no_abstract():
    respx.get("https://api.duckduckgo.com/").mock(
        return_value=httpx.Response(200, json={
            "Abstract": "",
            "AbstractURL": "",
            "RelatedTopics": [
                {"Text": "Only topic", "FirstURL": "https://example.com/1"},
                {"Text": "Second topic", "FirstURL": "https://example.com/2"},
            ],
        })
    )
    results = search_web("test", max_results=1)
    assert len(results) == 1
    assert results[0]["snippet"] == "Only topic"
