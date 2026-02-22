# Phil Learning Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Phil a continuously learning agent with persistent fact memory, RLHF feedback, and web search.

**Architecture:** New `MemoryStore` (SQLite metadata + ChromaDB embeddings) stores distilled facts extracted automatically from chats, mails, calendar events, and tasks. Facts are injected as context in every chat. Thumbs up/down on Phil chat bubbles drive confidence updates. A new Memory Control Panel (sidebar tab) shows all stored facts for oversight and correction.

**Tech Stack:** Python sqlite3, chromadb, httpx, FastAPI, React/TypeScript, Zustand, CSS Modules

---

## Background & File Map

```
webapp/
  backend/
    main.py              (1276 lines) — FastAPI app; add memory init + endpoints + chat integration
    memory_store.py      (NEW)        — MemoryStore: SQLite + ChromaDB dual layer
    web_search.py        (NEW)        — DuckDuckGo Instant Answer wrapper
    knowledge_store.py   (existing)   — mail RAG, use as pattern for ChromaDB usage
    llm_client.py        (existing)   — HybridLLMClient, task kinds

  frontend/src/
    api/client.ts        (existing)   — add memory API methods
    api/types.ts         (existing)   — add MemoryFact type
    store/useStore.ts    (existing)   — View type: add 'memory', add memoryCount state
    components/
      Phil/PhilPanel.tsx (existing)   — ChatMessage.fact_ids, thumbs up/down buttons
      Phil/PhilPanel.module.css       — thumbs button styles
      Views/MemoryView.tsx   (NEW)    — control panel table
      Views/MemoryView.module.css (NEW)
      Layout/Sidebar.tsx (existing)   — add 🧠 nav item + badge

  tests/
    test_memory_store.py (NEW)

  data/
    memory.db            (auto-created at runtime under ./data/)
```

### Key existing patterns to follow
- `knowledge_store.py` — ChromaDB collection setup with fake EF in tests (see `test_knowledge_store.py`)
- `main.py:28-43` — try/except init pattern for optional stores
- `main.py:907-973` — `/api/chat` endpoint + SSE streaming pattern
- `PhilPanel.tsx:498-531` — message rendering loop (where to add thumbs)
- `useStore.ts:4` — `View` union type; `Sidebar.tsx:49-54` — NAV_ITEMS array

---

## Task 1: MemoryStore — SQLite layer

**Files:**
- Create: `backend/memory_store.py`
- Create: `tests/test_memory_store.py`

### Step 1: Write the failing tests

```python
# tests/test_memory_store.py
import sqlite3
import pytest
from backend.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    """SQLite-only store (ChromaDB skipped via mock)."""
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
    s._chroma_collection = None  # skip ChromaDB in unit tests
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
    assert store.list_facts()[0]["confidence"] >= 0.10


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
```

### Step 2: Run tests — expect FAIL

```bash
cd "/Users/robert/Library/CloudStorage/OneDrive-Persönlich/Vorlesungen/Datenbasierte Fallstudien/Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp"
python -m pytest tests/test_memory_store.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'backend.memory_store'`

### Step 3: Implement MemoryStore SQLite layer

```python
# backend/memory_store.py
from __future__ import annotations
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ChromaDB import is optional — if unavailable, semantic search degrades to SQL LIKE
try:
    import chromadb
    from chromadb import EmbeddingFunction, Documents, Embeddings
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

_BASE_CONFIDENCE: dict[str, float] = {
    "chat": 0.70,
    "mail": 0.60,
    "calendar": 0.60,
    "task": 0.60,
    "web": 0.80,
}
_CONFIDENCE_UP   = 0.05
_CONFIDENCE_DOWN = 0.10
_CONFIDENCE_MIN  = 0.10
_CONFIDENCE_MAX  = 1.00
_INJECT_THRESHOLD = 0.30  # facts below this confidence are never injected as context

COLLECTION = "phil_facts"


class MemoryStore:
    """Persistent fact memory: SQLite for metadata, ChromaDB for semantic retrieval."""

    def __init__(
        self,
        db_path: str = "./data/memory.db",
        chroma_path: str = "/tmp/phil_chroma",
        openai_api_key: str = "",
    ):
        import os
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
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
        self._conn.commit()

        # ChromaDB layer — optional
        self._chroma_collection = None
        if _CHROMA_AVAILABLE:
            api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
            if api_key:
                try:
                    ef = OpenAIEmbeddingFunction(
                        api_key=api_key,
                        model_name="text-embedding-3-small",
                    )
                    client = chromadb.PersistentClient(path=chroma_path)
                    self._chroma_collection = client.get_or_create_collection(
                        COLLECTION,
                        embedding_function=ef,
                        metadata={"hnsw:space": "cosine"},
                    )
                except Exception as exc:
                    logging.warning(f"[Memory] ChromaDB init fehlgeschlagen: {exc}")

    # ── Write operations ────────────────────────────────────────────────────

    def upsert_fact(
        self,
        fact_id: str,
        text: str,
        category: str,
        source: str,
        source_ref: str | None = None,
        confidence: float | None = None,
    ) -> None:
        """Insert or update a fact. confidence defaults to source-based value."""
        base = confidence if confidence is not None else _BASE_CONFIDENCE.get(source, 0.65)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("""
            INSERT INTO facts (id, text, category, source, source_ref, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                category=excluded.category,
                source_ref=excluded.source_ref
        """, (fact_id, text, category, source, source_ref, base, now))
        self._conn.commit()

        if self._chroma_collection is not None:
            try:
                self._chroma_collection.upsert(
                    ids=[fact_id],
                    documents=[text],
                    metadatas=[{"category": category, "source": source}],
                )
            except Exception as exc:
                logging.warning(f"[Memory] ChromaDB upsert fehlgeschlagen: {exc}")

    def apply_feedback(self, fact_id: str, rating: str) -> None:
        """rating='up' → +0.05 confidence; 'down' → -0.10, clamped to [0.10, 1.00]."""
        col = "positive_votes" if rating == "up" else "negative_votes"
        delta = _CONFIDENCE_UP if rating == "up" else -_CONFIDENCE_DOWN
        self._conn.execute(f"""
            UPDATE facts
            SET {col} = {col} + 1,
                confidence = MAX({_CONFIDENCE_MIN}, MIN({_CONFIDENCE_MAX}, confidence + ?))
            WHERE id = ?
        """, (delta, fact_id))
        self._conn.commit()

    def delete_fact(self, fact_id: str) -> None:
        self._conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self._conn.commit()
        if self._chroma_collection is not None:
            try:
                self._chroma_collection.delete(ids=[fact_id])
            except Exception as exc:
                logging.warning(f"[Memory] ChromaDB delete fehlgeschlagen: {exc}")

    def update_fact(
        self,
        fact_id: str,
        text: str | None = None,
        correction_note: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("""
            UPDATE facts
            SET text = COALESCE(?, text),
                correction_note = COALESCE(?, correction_note),
                corrected_at = ?
            WHERE id = ?
        """, (text, correction_note, now, fact_id))
        self._conn.commit()
        if text and self._chroma_collection is not None:
            try:
                row = self._conn.execute(
                    "SELECT category, source FROM facts WHERE id = ?", (fact_id,)
                ).fetchone()
                if row:
                    self._chroma_collection.upsert(
                        ids=[fact_id],
                        documents=[text],
                        metadatas=[{"category": row[0], "source": row[1]}],
                    )
            except Exception as exc:
                logging.warning(f"[Memory] ChromaDB update fehlgeschlagen: {exc}")

    # ── Read operations ─────────────────────────────────────────────────────

    def list_facts(
        self,
        category: str | None = None,
        min_confidence: float | None = None,
        source_ref: str | None = None,
    ) -> list[dict]:
        query = "SELECT id, text, category, source, source_ref, confidence, positive_votes, negative_votes, created_at, corrected_at, correction_note FROM facts WHERE 1=1"
        params: list = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if min_confidence is not None:
            query += " AND confidence >= ?"
            params.append(min_confidence)
        if source_ref:
            query += " AND source_ref = ?"
            params.append(source_ref)
        query += " ORDER BY confidence DESC, created_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        cols = ["id", "text", "category", "source", "source_ref", "confidence",
                "positive_votes", "negative_votes", "created_at", "corrected_at", "correction_note"]
        return [dict(zip(cols, r)) for r in rows]

    def search_facts(self, query: str, n_results: int = 10) -> list[dict]:
        """Return top-n semantically relevant facts above inject threshold.
        Falls back to SQL LIKE if ChromaDB unavailable."""
        if self._chroma_collection is not None and self._chroma_collection.count() > 0:
            try:
                n = min(n_results, self._chroma_collection.count())
                res = self._chroma_collection.query(
                    query_texts=[query],
                    n_results=n,
                    include=["metadatas", "distances"],
                )
                ids = res["ids"][0]
                if not ids:
                    return []
                placeholders = ",".join("?" * len(ids))
                rows = self._conn.execute(
                    f"SELECT id, text, category, source, confidence FROM facts WHERE id IN ({placeholders}) AND confidence >= ?",
                    ids + [_INJECT_THRESHOLD],
                ).fetchall()
                id_order = {fid: i for i, fid in enumerate(ids)}
                rows.sort(key=lambda r: id_order.get(r[0], 999))
                return [{"id": r[0], "text": r[1], "category": r[2], "source": r[3], "confidence": r[4]} for r in rows]
            except Exception as exc:
                logging.warning(f"[Memory] ChromaDB search fehlgeschlagen: {exc}")
        # Fallback: return all facts above threshold, ordered by confidence
        rows = self._conn.execute(
            "SELECT id, text, category, source, confidence FROM facts WHERE confidence >= ? ORDER BY confidence DESC LIMIT ?",
            (_INJECT_THRESHOLD, n_results),
        ).fetchall()
        return [{"id": r[0], "text": r[1], "category": r[2], "source": r[3], "confidence": r[4]} for r in rows]

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        by_cat = self._conn.execute(
            "SELECT category, COUNT(*), AVG(confidence) FROM facts GROUP BY category"
        ).fetchall()
        return {
            "total": total,
            "by_category": [
                {"category": r[0], "count": r[1], "avg_confidence": round(r[2], 3)}
                for r in by_cat
            ],
        }

    def build_context_block(self, query: str) -> str:
        """Return formatted memory block for chat prompt injection."""
        facts = self.search_facts(query, n_results=10)
        if not facts:
            return ""
        lines = ["\n=== PHIL'S GEDÄCHTNIS (gespeicherte Fakten) ==="]
        for f in facts:
            pct = int(f["confidence"] * 100)
            lines.append(f"  [{f['category']}] {f['text']}  (Konfidenz: {pct}%)")
        return "\n".join(lines)
```

### Step 4: Run tests — expect PASS

```bash
python -m pytest tests/test_memory_store.py -v
```

Expected: all 11 tests PASS

### Step 5: Commit

```bash
git add backend/memory_store.py tests/test_memory_store.py
git commit -m "feat(memory): MemoryStore SQLite+ChromaDB dual layer with RLHF feedback"
```

---

## Task 2: WebSearch module

**Files:**
- Create: `backend/web_search.py`
- Modify: `backend/requirements.txt` (verify `httpx` is listed, add if missing)

### Step 1: Write the failing test (append to `tests/test_memory_store.py`)

```python
# append to tests/test_memory_store.py

import httpx
from backend.web_search import search_web, WEB_SEARCH_TRIGGER_RE


def test_web_search_trigger_regex():
    assert WEB_SEARCH_TRIGGER_RE.search("Recherchiere mal Flaschenpost")
    assert WEB_SEARCH_TRIGGER_RE.search("was ist Flaschenpost?")
    assert WEB_SEARCH_TRIGGER_RE.search("Wer ist Max Müller")
    assert not WEB_SEARCH_TRIGGER_RE.search("Zeige mir den Kalender")


def test_search_web_returns_snippets(respx_mock):
    """Mock DuckDuckGo response."""
    respx_mock.get("https://api.duckduckgo.com/").mock(
        return_value=httpx.Response(200, json={
            "Abstract": "Flaschenpost ist ein Getränkelieferdienst.",
            "AbstractURL": "https://example.com",
            "RelatedTopics": [
                {"Text": "Gegründet 2016", "FirstURL": "https://example.com/2"},
            ],
        })
    )
    results = search_web("Flaschenpost")
    assert len(results) >= 1
    assert any("Getränkelieferdienst" in r["snippet"] for r in results)
```

### Step 2: Run tests — expect FAIL

```bash
python -m pytest tests/test_memory_store.py::test_web_search_trigger_regex tests/test_memory_store.py::test_search_web_returns_snippets -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'backend.web_search'`

### Step 3: Implement WebSearch

First check if `httpx` is in requirements:
```bash
grep httpx "/Users/robert/Library/CloudStorage/OneDrive-Persönlich/Vorlesungen/Datenbasierte Fallstudien/Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/backend/requirements.txt"
```
If missing, add `httpx` to `requirements.txt`.

Also install `respx` for tests if missing:
```bash
pip install respx httpx --quiet
```

```python
# backend/web_search.py
from __future__ import annotations
import logging
import re

import httpx

# Trigger pattern — if user message matches, run web search
WEB_SEARCH_TRIGGER_RE = re.compile(
    r'recherchiere|suche\s+mal|was\s+ist|wer\s+ist|was\s+bedeutet',
    re.IGNORECASE,
)

_DDGO_URL = "https://api.duckduckgo.com/"
_TIMEOUT = 5.0


def search_web(query: str, max_results: int = 3) -> list[dict]:
    """Query DuckDuckGo Instant Answer API (no key needed).

    Returns list of {"snippet": str, "url": str}.
    Returns [] on any error (non-blocking).
    """
    try:
        resp = httpx.get(
            _DDGO_URL,
            params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logging.warning(f"[WebSearch] DuckDuckGo fehlgeschlagen: {exc}")
        return []

    results: list[dict] = []
    if data.get("Abstract"):
        results.append({"snippet": data["Abstract"], "url": data.get("AbstractURL", "")})
    for topic in data.get("RelatedTopics", [])[:max_results]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({"snippet": topic["Text"], "url": topic.get("FirstURL", "")})
    return results[:max_results]


def build_web_context(query: str) -> tuple[str, list[dict]]:
    """Run search and return (context_block, raw_results).

    context_block is empty string if no results.
    raw_results are used for fact extraction.
    """
    results = search_web(query)
    if not results:
        return "", []
    lines = [f"\n=== WEBSUCHE: '{query}' ==="]
    for r in results:
        lines.append(f"  {r['snippet']}")
        if r["url"]:
            lines.append(f"  Quelle: {r['url']}")
    return "\n".join(lines), results
```

### Step 4: Run tests — expect PASS

```bash
python -m pytest tests/test_memory_store.py -v -k "web_search"
```

Expected: 2 tests PASS

### Step 5: Commit

```bash
git add backend/web_search.py tests/test_memory_store.py backend/requirements.txt
git commit -m "feat(memory): WebSearch DuckDuckGo wrapper + trigger regex"
```

---

## Task 3: Memory API endpoints in main.py

**Files:**
- Modify: `backend/main.py`

### Step 1: Initialise MemoryStore (after line 43 in main.py, after `ontology_store` block)

Add these imports at the top of `main.py` (after existing imports around line 26):

```python
from backend.memory_store import MemoryStore
from backend.web_search import WEB_SEARCH_TRIGGER_RE, build_web_context
```

Add after the `ontology_store` try/except block (after line 43):

```python
try:
    memory_store = MemoryStore(
        db_path="./data/memory.db",
        chroma_path="/tmp/phil_chroma",
    )
except Exception as e:
    logging.warning(f"[Memory] MemoryStore deaktiviert: {type(e).__name__}: {e}")
    memory_store = None
```

### Step 2: Add Pydantic models (add near other BaseModel classes, e.g. after `BriefingRequest` around line 982)

```python
class MemoryFeedbackRequest(BaseModel):
    fact_id: str
    rating: str  # "up" | "down"

class MemoryUpdateRequest(BaseModel):
    text: str | None = None
    correction_note: str | None = None
```

### Step 3: Add API endpoints (add after the briefing endpoint, around line 1075)

```python
# ── Memory / Learning API ─────────────────────────────────────────────────────

@app.get("/api/memory/facts")
def memory_list_facts(
    category: str | None = None,
    min_confidence: float | None = None,
    source_ref: str | None = None,
    session_id: str | None = Cookie(default=None),
):
    _get_session(session_id)
    if memory_store is None:
        return {"facts": []}
    return {"facts": memory_store.list_facts(
        category=category,
        min_confidence=min_confidence,
        source_ref=source_ref,
    )}


@app.delete("/api/memory/facts/{fact_id}")
def memory_delete_fact(fact_id: str, session_id: str | None = Cookie(default=None)):
    _get_session(session_id)
    if memory_store is None:
        raise HTTPException(status_code=503, detail="MemoryStore nicht verfügbar")
    memory_store.delete_fact(fact_id)
    return {"ok": True}


@app.patch("/api/memory/facts/{fact_id}")
def memory_update_fact(
    fact_id: str,
    req: MemoryUpdateRequest,
    session_id: str | None = Cookie(default=None),
):
    _get_session(session_id)
    if memory_store is None:
        raise HTTPException(status_code=503, detail="MemoryStore nicht verfügbar")
    memory_store.update_fact(fact_id, text=req.text, correction_note=req.correction_note)
    return {"ok": True}


@app.post("/api/memory/feedback")
def memory_feedback(req: MemoryFeedbackRequest, session_id: str | None = Cookie(default=None)):
    _get_session(session_id)
    if memory_store is None:
        raise HTTPException(status_code=503, detail="MemoryStore nicht verfügbar")
    if req.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating muss 'up' oder 'down' sein")
    memory_store.apply_feedback(req.fact_id, req.rating)
    return {"ok": True}


@app.get("/api/memory/stats")
def memory_stats(session_id: str | None = Cookie(default=None)):
    _get_session(session_id)
    if memory_store is None:
        return {"total": 0, "by_category": []}
    return memory_store.stats()
```

### Step 4: Verify the server starts cleanly

```bash
cd "/Users/robert/Library/CloudStorage/OneDrive-Persönlich/Vorlesungen/Datenbasierte Fallstudien/Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp"
python -c "import backend.main; print('OK')"
```

Expected: `OK` (no ImportError)

### Step 5: Commit

```bash
git add backend/main.py
git commit -m "feat(memory): /api/memory/* endpoints (list, delete, patch, feedback, stats)"
```

---

## Task 4: Chat integration — memory injection + fact extraction + web search

**Files:**
- Modify: `backend/main.py` (the `/api/chat` endpoint, lines ~840–973)

### Step 1: Extend `ChatRequest` with `message_id`

Find `class ChatRequest` (line 840) and change to:

```python
class ChatRequest(BaseModel):
    message: str
    include_context: bool = True
    message_id: str = ""  # uuid4 from frontend; used to tag extracted facts
```

### Step 2: Add fact extraction helper (add near `_build_rag_context`, around line 845)

```python
FACT_EXTRACTION_SYSTEM = """\
Extrahiere aus diesem Gespräch maximal 3 neue, konkrete Fakten über Personen,
Projekte, Konzepte, Orte oder Abläufe.
Nur wirklich neue Informationen — keine allgemeinen Aussagen.
Antworte ausschließlich mit validem JSON (kein Markdown):
[{"text": "...", "category": "Person|Projekt|Konzept|Prozedur|Ort", "confidence": 0.7}]
Wenn keine neuen Fakten: []
"""


def _extract_and_store_facts(user_msg: str, phil_response: str, message_id: str) -> None:
    """Run async LLM fact extraction and store results in memory_store.
    Called after chat streaming completes. Errors are swallowed — non-blocking.
    """
    if memory_store is None:
        return
    try:
        llm = get_llm_client("cloud")
        prompt = f"[Nutzer]: {user_msg[:400]}\n[Phil]: {phil_response[:800]}"
        raw = llm.create(task="entities", prompt=prompt, max_tokens=256, system=FACT_EXTRACTION_SYSTEM)
        import json as _json
        # Strip markdown fences if model wraps JSON
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        facts = _json.loads(raw.strip())
        if not isinstance(facts, list):
            return
        for f in facts[:3]:
            if not isinstance(f, dict) or not f.get("text") or not f.get("category"):
                continue
            fact_id = str(uuid.uuid4())
            memory_store.upsert_fact(
                fact_id=fact_id,
                text=f["text"],
                category=f["category"],
                source="chat",
                source_ref=message_id or None,
                confidence=float(f.get("confidence", 0.7)),
            )
            logging.info(f"[Memory] Fakt gespeichert: [{f['category']}] {f['text'][:60]}")
    except Exception as exc:
        logging.warning(f"[Memory] Fact-Extraction fehlgeschlagen: {exc}")
```

### Step 3: Modify `/api/chat` to inject memory context and run web search

Find the `chat()` function (line 908). After the `graph_str` block (around line 946) and before building `user_msg`, add:

```python
        # Memory: inject relevant stored facts
        memory_str = ""
        if memory_store is not None:
            try:
                memory_str = memory_store.build_context_block(req.message)
                if memory_str:
                    context_str += memory_str
            except Exception as exc:
                logging.warning(f"[Memory] Kontext fehlgeschlagen: {exc}")

        # Web search: trigger on keywords, inject results + store as facts
        web_str = ""
        if WEB_SEARCH_TRIGGER_RE.search(req.message):
            try:
                web_str, web_results = build_web_context(req.message)
                if web_str:
                    context_str += web_str
                    # Store web snippets as facts
                    if memory_store is not None:
                        for wr in web_results:
                            memory_store.upsert_fact(
                                fact_id=str(uuid.uuid4()),
                                text=wr["snippet"][:200],
                                category="Konzept",
                                source="web",
                                source_ref=req.message[:80],
                            )
            except Exception as exc:
                logging.warning(f"[Memory] Web-Suche fehlgeschlagen: {exc}")
```

### Step 4: Capture full response for async fact extraction

In the `generate()` function inside `chat()`, accumulate the full response text and call extraction after `[DONE]`. Replace the existing `generate()` with:

```python
    # Capture full Phil response for async fact extraction
    _full_response: list[str] = []

    def generate():
        stream_kwargs = dict(task="chat", prompt=user_msg, max_tokens=1024, system=PHIL_SYSTEM)
        try:
            for text in llm.stream(**stream_kwargs):
                _full_response.append(text)
                yield f"data: {text}\n\n"
        except Exception as exc:
            logging.warning(f"[Chat] LLM '{getattr(llm, 'mode', '?')}' fehlgeschlagen: {exc}")
            if getattr(llm, 'mode', 'cloud') != 'cloud':
                logging.warning("[Chat] Fallback auf Cloud-LLM")
                try:
                    for text in get_llm_client("cloud").stream(**stream_kwargs):
                        _full_response.append(text)
                        yield f"data: {text}\n\n"
                except Exception as exc2:
                    logging.warning(f"[Chat] Cloud-Fallback fehlgeschlagen: {exc2}")
                    yield f"data: [Fehler: LLM nicht erreichbar ({type(exc2).__name__})]\n\n"
            else:
                yield f"data: [Fehler: LLM nicht erreichbar ({type(exc).__name__})]\n\n"
        # Async fact extraction after response is complete
        _extract_and_store_facts(req.message, "".join(_full_response), req.message_id)
        yield "data: [DONE]\n\n"
```

### Step 5: Verify import and syntax

```bash
python -c "import backend.main; print('OK')"
```

Expected: `OK`

### Step 6: Commit

```bash
git add backend/main.py
git commit -m "feat(memory): chat memory injection, web search trigger, async fact extraction"
```

---

## Task 5: Frontend — Memory API client methods

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`

### Step 1: Add `MemoryFact` type to `types.ts`

Find `types.ts` and add:

```typescript
export interface MemoryFact {
  id: string
  text: string
  category: 'Person' | 'Projekt' | 'Konzept' | 'Prozedur' | 'Ort' | string
  source: 'chat' | 'mail' | 'calendar' | 'task' | 'web'
  source_ref: string | null
  confidence: number
  positive_votes: number
  negative_votes: number
  created_at: string
  corrected_at: string | null
  correction_note: string | null
}

export interface MemoryStats {
  total: number
  by_category: Array<{ category: string; count: number; avg_confidence: number }>
}
```

### Step 2: Add API methods to `client.ts`

In `client.ts`, add these methods to the `api` object (add after `briefingStream`):

```typescript
  memoryFacts: async (params?: {
    category?: string
    min_confidence?: number
    source_ref?: string
  }): Promise<{ facts: MemoryFact[] }> => {
    const q = new URLSearchParams()
    if (params?.category) q.set('category', params.category)
    if (params?.min_confidence != null) q.set('min_confidence', String(params.min_confidence))
    if (params?.source_ref) q.set('source_ref', params.source_ref)
    const res = await fetch(`/api/memory/facts${q.size ? '?' + q : ''}`, { credentials: 'include' })
    if (!res.ok) throw new Error('memory/facts failed')
    return res.json()
  },

  memoryFeedback: async (factId: string, rating: 'up' | 'down'): Promise<void> => {
    await fetch('/api/memory/feedback', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fact_id: factId, rating }),
    })
  },

  memoryDeleteFact: async (factId: string): Promise<void> => {
    await fetch(`/api/memory/facts/${factId}`, {
      method: 'DELETE',
      credentials: 'include',
    })
  },

  memoryUpdateFact: async (factId: string, text: string, note?: string): Promise<void> => {
    await fetch(`/api/memory/facts/${factId}`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, correction_note: note }),
    })
  },

  memoryStats: async (): Promise<MemoryStats> => {
    const res = await fetch('/api/memory/stats', { credentials: 'include' })
    if (!res.ok) throw new Error('memory/stats failed')
    return res.json()
  },
```

Also add the `MemoryFact` import to `client.ts`:
```typescript
import type { ..., MemoryFact, MemoryStats } from './types'
```

### Step 3: Commit

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts
git commit -m "feat(memory): frontend API client methods for memory CRUD + feedback"
```

---

## Task 6: Thumbs up/down on Phil chat bubbles

**Files:**
- Modify: `frontend/src/components/Phil/PhilPanel.tsx`
- Modify: `frontend/src/components/Phil/PhilPanel.module.css`

### Step 1: Extend `ChatMessage` interface and add `message_id` to requests

In `PhilPanel.tsx`, change the interface (line 11):

```typescript
interface ChatMessage {
  role: 'user' | 'phil'
  text: string
  messageId?: string       // uuid sent with the request (for feedback linking)
  feedback?: 'up' | 'down' | null  // user's thumbs vote on this message
}
```

### Step 2: Generate a message_id per send and pass to chatStream

In `PhilPanel.tsx`, add this import at the top:
```typescript
import { v4 as uuidv4 } from 'uuid'
```

If `uuid` is not installed:
```bash
cd "/Users/robert/Library/CloudStorage/OneDrive-Persönlich/Vorlesungen/Datenbasierte Fallstudien/Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend"
npm install uuid @types/uuid
```

In `send()`, before `setMessages((prev) => [...prev, { role: 'user', text }])`:
```typescript
    const msgId = uuidv4()
```

Change the `api.chatStream` call to pass `message_id`:
```typescript
      const stream = api.chatStream(contextMsg, !selection, msgId)
```

After streaming finishes (in the `finally` block), update the last Phil message to store the `messageId`:
```typescript
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last && last.role === 'phil') {
          updated[updated.length - 1] = { ...last, messageId: msgId }
        }
        return updated
      })
```

Update `chatStream` signature in `client.ts` to accept `messageId`:
```typescript
  chatStream: (message: string, includeContext: boolean = true, messageId: string = ''): ReadableStream<string> => {
    // ... existing SSE code, but POST body changes to:
    body: JSON.stringify({ message, include_context: includeContext, message_id: messageId }),
```

### Step 3: Add `handleFeedback` function in `PhilPanel.tsx`

```typescript
  async function handleFeedback(msg: ChatMessage, idx: number, rating: 'up' | 'down') {
    if (!msg.messageId || msg.feedback) return
    // Optimistic UI update
    setMessages((prev) => prev.map((m, i) =>
      i === idx ? { ...m, feedback: rating } : m
    ))
    // Fetch facts extracted for this message_id and apply feedback
    try {
      const { facts } = await api.memoryFacts({ source_ref: msg.messageId })
      await Promise.all(facts.map((f) => api.memoryFeedback(f.id, rating)))
    } catch {
      // silent — feedback is best-effort
    }
  }
```

### Step 4: Add thumbs buttons to Phil message bubbles

In the messages render loop, find where the TTS button is rendered (around line 510):

```tsx
                {msg.role === 'phil' && msg.text && !(streaming && i === messages.length - 1) && (
                  <div className={styles.msgActions}>
                    <button
                      className={`${styles.msgTtsBtn} ${ttsIdx === i ? styles.msgTtsBtnPlaying : ''}`}
                      onClick={() => toggleTts(msg.text, i)}
                      disabled={ttsLoadingIdx === i}
                      title={ttsIdx === i ? 'Pause' : 'Vorlesen'}
                      aria-label={ttsIdx === i ? 'Pause' : 'Vorlesen'}
                    >
                      {ttsLoadingIdx === i ? '…' : ttsIdx === i ? '⏸' : '▶'}
                    </button>
                    {msg.messageId && (
                      <>
                        <button
                          className={`${styles.thumbBtn} ${msg.feedback === 'up' ? styles.thumbUp : ''}`}
                          onClick={() => handleFeedback(msg, i, 'up')}
                          disabled={!!msg.feedback}
                          title="Hilfreich"
                          aria-label="Hilfreich"
                        >👍</button>
                        <button
                          className={`${styles.thumbBtn} ${msg.feedback === 'down' ? styles.thumbDown : ''}`}
                          onClick={() => handleFeedback(msg, i, 'down')}
                          disabled={!!msg.feedback}
                          title="Nicht hilfreich"
                          aria-label="Nicht hilfreich"
                        >👎</button>
                      </>
                    )}
                  </div>
                )}
```

Wrap the existing TTS button in `<div className={styles.msgActions}>` and close it after the thumbs buttons.

### Step 5: Add CSS in `PhilPanel.module.css`

```css
.msgActions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.thumbBtn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.4;
  padding: 2px 4px;
  border-radius: 4px;
  transition: opacity 0.15s, background 0.15s;
  line-height: 1;
}
.thumbBtn:hover:not(:disabled) { opacity: 1; background: #f0f0f0; }
.thumbBtn:disabled { cursor: default; }
.thumbUp  { opacity: 1; }
.thumbDown { opacity: 1; }
```

### Step 6: Commit

```bash
git add frontend/src/components/Phil/PhilPanel.tsx frontend/src/components/Phil/PhilPanel.module.css frontend/src/api/client.ts
git commit -m "feat(memory): thumbs up/down on Phil chat bubbles with RLHF feedback"
```

---

## Task 7: MemoryView control panel

**Files:**
- Create: `frontend/src/components/Views/MemoryView.tsx`
- Create: `frontend/src/components/Views/MemoryView.module.css`

### Step 1: Create `MemoryView.tsx`

```tsx
// frontend/src/components/Views/MemoryView.tsx
import { useState, useEffect, useCallback } from 'react'
import { api } from '../../api/client'
import type { MemoryFact } from '../../api/types'
import styles from './MemoryView.module.css'

const CATEGORIES = ['Alle', 'Person', 'Projekt', 'Konzept', 'Prozedur', 'Ort']

export function MemoryView() {
  const [facts, setFacts] = useState<MemoryFact[]>([])
  const [loading, setLoading] = useState(true)
  const [categoryFilter, setCategoryFilter] = useState('Alle')
  const [minConfidence, setMinConfidence] = useState(0)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = {}
      if (categoryFilter !== 'Alle') params.category = categoryFilter
      if (minConfidence > 0) params.min_confidence = minConfidence / 100
      const { facts: data } = await api.memoryFacts(params as Parameters<typeof api.memoryFacts>[0])
      setFacts(data)
    } catch { /* silent */ }
    finally { setLoading(false) }
  }, [categoryFilter, minConfidence])

  useEffect(() => { load() }, [load])

  async function handleDelete(id: string) {
    await api.memoryDeleteFact(id)
    setFacts((prev) => prev.filter((f) => f.id !== id))
  }

  async function handleSaveEdit(id: string) {
    await api.memoryUpdateFact(id, editText, 'Manuell korrigiert')
    setFacts((prev) => prev.map((f) => f.id === id ? { ...f, text: editText } : f))
    setEditingId(null)
  }

  function startEdit(fact: MemoryFact) {
    setEditingId(fact.id)
    setEditText(fact.text)
  }

  function confidenceColor(c: number) {
    if (c >= 0.75) return '#059669'
    if (c >= 0.5)  return '#D97706'
    return '#DC2626'
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>🧠 Phil's Gedächtnis</h2>
        <span className={styles.count}>{facts.length} Fakten</span>
        <button className={styles.refreshBtn} onClick={load} disabled={loading}>↺</button>
      </div>

      <div className={styles.filters}>
        <div className={styles.categoryChips}>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              className={`${styles.chip} ${categoryFilter === cat ? styles.chipActive : ''}`}
              onClick={() => setCategoryFilter(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
        <label className={styles.confidenceLabel}>
          Min. Konfidenz: {minConfidence}%
          <input
            type="range" min={0} max={90} step={10}
            value={minConfidence}
            onChange={(e) => setMinConfidence(Number(e.target.value))}
            className={styles.slider}
          />
        </label>
      </div>

      {loading && <div className={styles.empty}>Lade…</div>}
      {!loading && facts.length === 0 && (
        <div className={styles.empty}>Noch keine Fakten gespeichert.</div>
      )}

      {!loading && facts.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Fakt</th>
                <th>Kategorie</th>
                <th>Quelle</th>
                <th>Konfidenz</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {facts.map((f) => (
                <tr key={f.id}>
                  <td className={styles.textCell}>
                    {editingId === f.id ? (
                      <input
                        className={styles.editInput}
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveEdit(f.id)
                          if (e.key === 'Escape') setEditingId(null)
                        }}
                        autoFocus
                      />
                    ) : (
                      <span title={f.correction_note ?? undefined}>{f.text}</span>
                    )}
                  </td>
                  <td><span className={styles.categoryBadge}>{f.category}</span></td>
                  <td className={styles.sourceCell}>
                    <span className={styles.sourceBadge} data-source={f.source}>{f.source}</span>
                    {f.source_ref && <span className={styles.sourceRef} title={f.source_ref}>…</span>}
                  </td>
                  <td>
                    <div className={styles.confBar}>
                      <div
                        className={styles.confFill}
                        style={{
                          width: `${Math.round(f.confidence * 100)}%`,
                          background: confidenceColor(f.confidence),
                        }}
                      />
                      <span className={styles.confLabel}>{Math.round(f.confidence * 100)}%</span>
                    </div>
                  </td>
                  <td className={styles.actionsCell}>
                    {editingId === f.id ? (
                      <>
                        <button className={styles.actionBtn} onClick={() => handleSaveEdit(f.id)} title="Speichern">✓</button>
                        <button className={styles.actionBtn} onClick={() => setEditingId(null)} title="Abbrechen">✕</button>
                      </>
                    ) : (
                      <>
                        <button className={styles.actionBtn} onClick={() => startEdit(f)} title="Bearbeiten">✏</button>
                        <button className={`${styles.actionBtn} ${styles.deleteBtn}`} onClick={() => handleDelete(f.id)} title="Löschen">🗑</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
```

### Step 2: Create `MemoryView.module.css`

```css
.container { display: flex; flex-direction: column; height: 100%; padding: 24px; gap: 16px; overflow: hidden; }
.header { display: flex; align-items: center; gap: 12px; }
.title { font-size: 20px; font-weight: 600; color: #111; margin: 0; }
.count { font-size: 13px; color: #6B7280; background: #F3F4F6; padding: 2px 8px; border-radius: 12px; }
.refreshBtn { background: none; border: 1px solid #E5E7EB; border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 16px; color: #6B7280; }
.refreshBtn:hover { background: #F9FAFB; }

.filters { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.categoryChips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { background: #F3F4F6; border: 1px solid #E5E7EB; border-radius: 16px; padding: 4px 12px; font-size: 13px; cursor: pointer; color: #374151; }
.chip:hover { background: #E5E7EB; }
.chipActive { background: #1D4ED8; color: #fff; border-color: #1D4ED8; }

.confidenceLabel { font-size: 13px; color: #6B7280; display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.slider { width: 120px; accent-color: #1D4ED8; }

.empty { color: #9CA3AF; font-size: 14px; padding: 32px 0; text-align: center; }
.tableWrap { overflow-y: auto; flex: 1; border: 1px solid #E5E7EB; border-radius: 8px; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th { background: #F9FAFB; padding: 10px 12px; text-align: left; font-weight: 500; color: #6B7280; border-bottom: 1px solid #E5E7EB; position: sticky; top: 0; }
.table td { padding: 10px 12px; border-bottom: 1px solid #F3F4F6; vertical-align: middle; }
.table tr:last-child td { border-bottom: none; }
.table tr:hover td { background: #FAFAFA; }

.textCell { max-width: 360px; word-break: break-word; color: #111; }
.editInput { width: 100%; border: 1px solid #6366F1; border-radius: 4px; padding: 4px 8px; font-size: 13px; outline: none; }

.categoryBadge { background: #EEF2FF; color: #4338CA; border-radius: 12px; padding: 2px 8px; font-size: 12px; font-weight: 500; }

.sourceCell { display: flex; align-items: center; gap: 4px; }
.sourceBadge { font-size: 11px; border-radius: 4px; padding: 2px 6px; font-weight: 500; }
.sourceBadge[data-source="chat"]     { background: #D1FAE5; color: #065F46; }
.sourceBadge[data-source="mail"]     { background: #DBEAFE; color: #1E40AF; }
.sourceBadge[data-source="calendar"] { background: #FEF3C7; color: #92400E; }
.sourceBadge[data-source="task"]     { background: #F3E8FF; color: #6B21A8; }
.sourceBadge[data-source="web"]      { background: #FFE4E6; color: #9F1239; }
.sourceRef { color: #9CA3AF; font-size: 11px; cursor: default; }

.confBar { display: flex; align-items: center; gap: 6px; }
.confBarTrack { position: relative; width: 60px; height: 6px; background: #E5E7EB; border-radius: 3px; overflow: hidden; }
.confFill { height: 6px; border-radius: 3px; transition: width 0.3s; }
.confLabel { font-size: 11px; color: #6B7280; min-width: 32px; }

.actionsCell { white-space: nowrap; }
.actionBtn { background: none; border: none; cursor: pointer; padding: 4px 6px; border-radius: 4px; font-size: 14px; color: #6B7280; }
.actionBtn:hover { background: #F3F4F6; color: #111; }
.deleteBtn:hover { background: #FEE2E2; color: #DC2626; }
```

### Step 3: Commit

```bash
git add frontend/src/components/Views/MemoryView.tsx frontend/src/components/Views/MemoryView.module.css
git commit -m "feat(memory): MemoryView control panel with filter, confidence bar, edit/delete"
```

---

## Task 8: Store + Sidebar — add memory nav tab

**Files:**
- Modify: `frontend/src/store/useStore.ts`
- Modify: `frontend/src/components/Layout/Sidebar.tsx`
- Modify: `frontend/src/App.tsx` (or wherever views are rendered — verify path)

### Step 1: Add 'memory' to View type in `useStore.ts`

Line 4, change:
```typescript
export type View = 'dashboard' | 'mails' | 'calendar' | 'tasks' | 'trains' | 'memory'
```

Add `memoryCount` state (total facts count for badge):
```typescript
  // Memory
  memoryCount: number
  setMemoryCount: (n: number) => void
```

In the initial state:
```typescript
  memoryCount: 0,
  setMemoryCount: (memoryCount) => set({ memoryCount }),
```

### Step 2: Add 🧠 nav item to `Sidebar.tsx`

Find the `NAV_ITEMS` array (around line 49) and add:
```typescript
const IconMemory = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="8" cy="8" r="6"/>
    <path d="M5 8c0-1.7 1.3-3 3-3s3 1.3 3 3"/>
    <circle cx="6.5" cy="9.5" r="1"/>
    <circle cx="9.5" cy="9.5" r="1"/>
  </svg>
)
```

```typescript
  { view: 'memory', label: 'Gedächtnis', icon: <IconMemory /> },
```

In the nav item render loop, add the badge for memory (similar to mails and tasks):
```tsx
            {item.view === 'memory' && memoryCount > 0 && (
              <span className={styles.badge}>{memoryCount}</span>
            )}
```

Destructure `memoryCount` from `useStore()` in the `Sidebar` component.

### Step 3: Load memory count on startup

In the component that loads initial data (check `App.tsx` or the main dashboard loader), add:
```typescript
  api.memoryStats()
    .then((stats) => useStore.getState().setMemoryCount(stats.total))
    .catch(() => {})
```

### Step 4: Wire `MemoryView` in the view router

Find where views are switched (likely a conditional render in `App.tsx` or `Layout.tsx`). Add:
```typescript
import { MemoryView } from './components/Views/MemoryView'

// In the view switch:
{view === 'memory' && <MemoryView />}
```

### Step 5: Refresh memory count after each chat

In `PhilPanel.tsx`, after the streaming `finally` block in `send()`, add:
```typescript
      api.memoryStats()
        .then((s) => useStore.getState().setMemoryCount(s.total))
        .catch(() => {})
```

### Step 6: Build and verify

```bash
cd "/Users/robert/Library/CloudStorage/OneDrive-Persönlich/Vorlesungen/Datenbasierte Fallstudien/Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend"
npm run build 2>&1 | tail -20
```

Expected: build succeeds, 0 TypeScript errors.

### Step 7: Run full test suite

```bash
cd "/Users/robert/Library/CloudStorage/OneDrive-Persönlich/Vorlesungen/Datenbasierte Fallstudien/Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp"
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass.

### Step 8: Commit

```bash
git add frontend/src/store/useStore.ts frontend/src/components/Layout/Sidebar.tsx frontend/src/App.tsx
git commit -m "feat(memory): 🧠 memory nav tab, badge, view routing, count refresh"
```

---

## Done

All 8 tasks implement the Phil Learning Agent:

| Task | Component | What it does |
|------|-----------|--------------|
| 1 | `memory_store.py` | SQLite+ChromaDB fact persistence + RLHF confidence |
| 2 | `web_search.py` | DuckDuckGo search on keyword trigger |
| 3 | `main.py` | Memory API endpoints |
| 4 | `main.py` | Chat memory injection + async fact extraction |
| 5 | `client.ts` / `types.ts` | Frontend API methods |
| 6 | `PhilPanel.tsx` | Thumbs up/down per Phil message |
| 7 | `MemoryView.tsx` | Control panel (filter, edit, delete) |
| 8 | `Sidebar.tsx` / `useStore.ts` | Nav tab + badge + view routing |
