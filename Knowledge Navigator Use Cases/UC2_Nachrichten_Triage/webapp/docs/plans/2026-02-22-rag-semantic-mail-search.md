# RAG Semantic Mail Search — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a persistent semantic search memory for Phil — every triaged mail gets embedded and stored in ChromaDB; Phil's chat and a new search endpoint retrieve the most relevant past mails by meaning, not just keyword.

**Architecture:** OpenAI `text-embedding-3-small` embeds mail text on triage; ChromaDB stores vectors locally under `webapp/data/chroma/`. On chat, the top-3 semantically similar past mails are prepended to Phil's context as "MAILHISTORIE". A `GET /api/knowledge/search` endpoint lets the frontend query directly, which PhilPanel uses to show cited sources after each answer.

**Tech Stack:** `chromadb>=0.5`, `openai` (already installed), FastAPI (backend unchanged), React/TypeScript (frontend), `pytest-mock` (tests)

**Working directory for all commands:** `UC2_Nachrichten_Triage/webapp/`

---

## Task 1: Backend — knowledge_store.py

**Files:**
- Create: `backend/knowledge_store.py`
- Test: `tests/test_knowledge_store.py`

**Step 1: Write the failing test**

```python
# tests/test_knowledge_store.py
import pytest
import chromadb
from backend.knowledge_store import KnowledgeStore


@pytest.fixture
def store(tmp_path):
    """In-memory ChromaDB store for tests (no OpenAI key needed)."""
    return KnowledgeStore(persist_path=str(tmp_path / "chroma"), openai_api_key="test-key")


def test_index_and_search(store, mocker):
    mocker.patch.object(
        store.collection._embedding_function,
        "__call__",
        return_value=[[0.1] * 1536],  # fake embedding
    )
    store.index_mail(
        mail_id="abc123",
        subject="Projektstatus Update",
        sender="mueller@example.com",
        date="2026-02-01",
        kategorie="Aktion nötig",
        summary="Projekt verzögert sich um zwei Wochen.",
        body_snippet="Hallo, leider müssen wir den Termin verschieben.",
    )
    mocker.patch.object(
        store.collection._embedding_function,
        "__call__",
        return_value=[[0.1] * 1536],
    )
    results = store.search("Projektverzögerung", n_results=1)
    assert len(results) == 1
    assert results[0]["id"] == "abc123"
    assert results[0]["subject"] == "Projektstatus Update"


def test_search_empty_store(store, mocker):
    mocker.patch.object(
        store.collection._embedding_function,
        "__call__",
        return_value=[[0.1] * 1536],
    )
    results = store.search("anything", n_results=3)
    assert results == []


def test_index_upsert_idempotent(store, mocker):
    mocker.patch.object(
        store.collection._embedding_function,
        "__call__",
        return_value=[[0.1] * 1536],
    )
    for _ in range(2):
        store.index_mail("id1", "Betreff", "a@b.de", "2026-01-01", "Info", "Summary", "Body")
    assert store.collection.count() == 1
```

**Step 2: Run test to verify it fails**

```bash
cd UC2_Nachrichten_Triage/webapp
python -m pytest tests/test_knowledge_store.py -v
```
Expected: `ERROR` — `backend/knowledge_store.py` not found.

**Step 3: Write the implementation**

```python
# backend/knowledge_store.py
from __future__ import annotations
import os
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction


class KnowledgeStore:
    """Persistent semantic mail index backed by ChromaDB + OpenAI embeddings."""

    COLLECTION = "phil_mails"

    def __init__(self, persist_path: str = "./data/chroma", openai_api_key: str = ""):
        ef = OpenAIEmbeddingFunction(
            api_key=openai_api_key or os.getenv("OPENAI_API_KEY", ""),
            model_name="text-embedding-3-small",
        )
        self._client = chromadb.PersistentClient(path=persist_path)
        self.collection = self._client.get_or_create_collection(
            self.COLLECTION,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    def index_mail(
        self,
        mail_id: str,
        subject: str,
        sender: str,
        date: str,
        kategorie: str,
        summary: str,
        body_snippet: str,
    ) -> None:
        """Embed and upsert a mail into the collection."""
        document = f"Betreff: {subject}\nVon: {sender}\nZusammenfassung: {summary}\n{body_snippet[:300]}"
        self.collection.upsert(
            ids=[mail_id],
            documents=[document],
            metadatas=[{
                "subject": subject,
                "sender": sender,
                "date": date,
                "kategorie": kategorie,
                "summary": summary,
            }],
        )

    def search(self, query: str, n_results: int = 3) -> list[dict]:
        """Return top-n semantically similar mails. Empty list if store is empty."""
        if self.collection.count() == 0:
            return []
        n = min(n_results, self.collection.count())
        res = self.collection.query(
            query_texts=[query],
            n_results=n,
            include=["metadatas", "distances"],
        )
        results = []
        for i, meta in enumerate(res["metadatas"][0]):
            score = 1.0 - (res["distances"][0][i])  # cosine: 1=identical
            results.append({
                "id": res["ids"][0][i],
                "subject": meta.get("subject", ""),
                "sender": meta.get("sender", ""),
                "date": meta.get("date", ""),
                "kategorie": meta.get("kategorie", ""),
                "summary": meta.get("summary", ""),
                "score": round(score, 3),
            })
        return results
```

**Step 4: Install chromadb**

```bash
pip install "chromadb>=0.5"
```

**Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_knowledge_store.py -v
```
Expected: 3 PASSED.

**Step 6: Commit**

```bash
git add backend/knowledge_store.py tests/test_knowledge_store.py
git commit -m "feat(rag): add KnowledgeStore — ChromaDB + OpenAI embeddings"
```

---

## Task 2: Backend — Auto-index mails after triage

**Files:**
- Modify: `backend/main.py` lines 74–103 (`AnalyzeRequest` + `analyze()`)
- Modify: `backend/requirements.txt`
- Test: `tests/test_api.py`

**Step 1: Add chromadb to requirements.txt**

In `backend/requirements.txt`, add:
```
chromadb>=0.5
```

**Step 2: Write the failing test**

In `tests/test_api.py`, add at the bottom:

```python
def test_analyze_indexes_mail_when_mail_id_provided(mocker):
    """After successful triage, the mail is indexed in the knowledge store."""
    mock_index = mocker.patch("backend.main.knowledge_store.index_mail")
    mocker.patch("backend.main.anthropic_client.messages.create",
        return_value=mocker.Mock(
            content=[mocker.Mock(text='{"kategorie":"VIP","priorität":1,"zusammenfassung":"Test","empfohlene_aktion":"Antworten","stimmung":0.5}')]
        )
    )
    response = client.post("/api/analyze", json={
        "email_text": "Von: test@example.com\nBetreff: Test\n\nTestinhalt",
        "mail_id": "mail-42",
        "subject": "Test",
        "sender": "test@example.com",
        "date": "2026-02-22",
    })
    assert response.status_code == 200
    mock_index.assert_called_once()
    call_kwargs = mock_index.call_args.kwargs
    assert call_kwargs["mail_id"] == "mail-42"
    assert call_kwargs["kategorie"] == "VIP"


def test_analyze_still_works_without_mail_id(mocker):
    """mail_id is optional — old callers without it must still work."""
    mocker.patch("backend.main.knowledge_store.index_mail")
    mocker.patch("backend.main.anthropic_client.messages.create",
        return_value=mocker.Mock(
            content=[mocker.Mock(text='{"kategorie":"Nur Info","priorität":3,"zusammenfassung":"ok","empfohlene_aktion":"Ignorieren","stimmung":0.0}')]
        )
    )
    response = client.post("/api/analyze", json={"email_text": "test"})
    assert response.status_code == 200
```

**Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_api.py::test_analyze_indexes_mail_when_mail_id_provided -v
```
Expected: FAIL — `mail_id` field not accepted yet.

**Step 4: Modify AnalyzeRequest and analyze() in main.py**

Find the `AnalyzeRequest` class (line ~74) and replace it:

```python
class AnalyzeRequest(BaseModel):
    email_text: str
    mail_id: str | None = None
    subject: str = ""
    sender: str = ""
    date: str = ""

    @field_validator("email_text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("email_text darf nicht leer sein")
        return v
```

Find the `analyze()` function (line ~86) and add the indexing call after `return json.loads(raw)` — i.e. parse the result first, then index, then return:

```python
@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    prompt = COSTAR_PROMPT.format(email_text=req.email_text)
    try:
        response = anthropic_client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIStatusError as e:
        status = e.status_code if hasattr(e, "status_code") else 500
        if status == 529 or status == 429:
            raise HTTPException(status_code=503, detail="KI-Dienst vorübergehend ausgelastet. Bitte kurz warten.")
        raise HTTPException(status_code=502, detail=f"Claude API Fehler: {e}")
    raw = _strip_fences(response.content[0].text)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Claude-Antwort kein gültiges JSON: {e}")

    # Index in knowledge base if mail_id provided (non-fatal)
    if req.mail_id:
        try:
            knowledge_store.index_mail(
                mail_id=req.mail_id,
                subject=req.subject,
                sender=req.sender,
                date=req.date,
                kategorie=result.get("kategorie", ""),
                summary=result.get("zusammenfassung", ""),
                body_snippet=req.email_text[:500],
            )
        except Exception as exc:
            import logging; logging.warning(f"[RAG] Indexierung fehlgeschlagen: {exc}")

    return result
```

Also add near the top of `main.py` (after imports, before the FastAPI app or after existing singleton setups):

```python
from backend.knowledge_store import KnowledgeStore
knowledge_store = KnowledgeStore()
```

**Step 5: Run tests**

```bash
python -m pytest tests/test_api.py::test_analyze_indexes_mail_when_mail_id_provided tests/test_api.py::test_analyze_still_works_without_mail_id -v
```
Expected: 2 PASSED.

**Step 6: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all tests pass (chromadb mocked in the two new tests, existing tests unaffected).

**Step 7: Commit**

```bash
git add backend/main.py backend/requirements.txt tests/test_api.py
git commit -m "feat(rag): auto-index mails in ChromaDB after triage"
```

---

## Task 3: Backend — GET /api/knowledge/search

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_api.py`

**Step 1: Write the failing test**

```python
def test_knowledge_search_requires_session():
    response = client.get("/api/knowledge/search?q=test")
    assert response.status_code == 401


def test_knowledge_search_returns_results(mocker):
    # Patch session check
    mocker.patch("backend.main._get_session", return_value={"username": "test"})
    mocker.patch("backend.main.knowledge_store.search", return_value=[
        {"id": "m1", "subject": "Projektstatus", "sender": "a@b.de",
         "date": "2026-01-15", "kategorie": "Aktion nötig",
         "summary": "Projekt verzögert", "score": 0.92},
    ])
    response = client.get("/api/knowledge/search?q=Projektverzögerung")
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["subject"] == "Projektstatus"
    assert data["results"][0]["score"] == 0.92
```

**Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_api.py::test_knowledge_search_requires_session tests/test_api.py::test_knowledge_search_returns_results -v
```
Expected: FAIL — endpoint doesn't exist.

**Step 3: Add endpoint to main.py** (add before the static file serving block at the bottom):

```python
@app.get("/api/knowledge/search")
def knowledge_search(
    q: str,
    n: int = 3,
    session_id: str | None = Cookie(default=None),
):
    """Semantische Suche in der Mail-Historiendatenbank."""
    _get_session(session_id)
    if not q.strip():
        return {"results": []}
    results = knowledge_store.search(q.strip(), n_results=min(n, 10))
    return {"results": results}
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_api.py::test_knowledge_search_requires_session tests/test_api.py::test_knowledge_search_returns_results -v
```
Expected: 2 PASSED.

**Step 5: Commit**

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat(rag): GET /api/knowledge/search endpoint"
```

---

## Task 4: Backend — Augment /api/chat with RAG context

**Files:**
- Modify: `backend/main.py` — `_build_context()` or `chat()`
- Test: `tests/test_api.py`

**Step 1: Write the failing test**

```python
def test_chat_includes_rag_context(mocker):
    """Knowledge base results appear in the prompt sent to Claude."""
    mocker.patch("backend.main._get_session", return_value={"username": "test"})
    mocker.patch("backend.main.fetch_emails", return_value=[])
    mocker.patch("backend.main.fetch_google_calendar", return_value=[])
    mocker.patch("backend.main.fetch_tasks", return_value=[])
    mocker.patch("backend.main.knowledge_store.search", return_value=[
        {"id": "m1", "subject": "Förderantrag 2025", "sender": "dfg@example.de",
         "date": "2025-11-01", "kategorie": "VIP",
         "summary": "DFG-Förderung genehmigt.", "score": 0.88},
    ])
    captured = {}
    def fake_stream(model, max_tokens, system, messages):
        captured["messages"] = messages
        return mocker.MagicMock(__enter__=lambda s: mocker.MagicMock(text_stream=iter(["ok"])), __exit__=mocker.MagicMock(return_value=False))
    mocker.patch("backend.main.anthropic_client.messages.stream", side_effect=fake_stream)

    client.post("/api/chat", json={"message": "Was war mit dem Förderantrag?", "include_context": True})
    user_content = captured["messages"][0]["content"]
    assert "MAILHISTORIE" in user_content
    assert "Förderantrag 2025" in user_content
```

**Step 2: Run to verify it fails**

```bash
python -m pytest tests/test_api.py::test_chat_includes_rag_context -v
```
Expected: FAIL — "MAILHISTORIE" not in content.

**Step 3: Add RAG retrieval to chat() in main.py**

Add a helper function above `chat()`:

```python
def _build_rag_context(query: str) -> str:
    """Retrieve semantically similar past mails and format as context block."""
    try:
        results = knowledge_store.search(query, n_results=3)
    except Exception:
        return ""
    if not results:
        return ""
    lines = ["\n=== MAILHISTORIE (semantisch ähnliche frühere Mails) ==="]
    for r in results:
        lines.append(
            f"  [{r['date']}] Von: {r['sender']} | Betreff: {r['subject']}"
            f" | Kategorie: {r['kategorie']} | Relevanz: {int(r['score']*100)}%"
            f"\n  Zusammenfassung: {r['summary']}"
        )
    return "\n".join(lines)
```

In `chat()`, after `context_str = _build_context(mails, cal, tasks)`, add:

```python
        # RAG: enrich with semantically similar past mails
        rag_str = _build_rag_context(req.message)
        if rag_str:
            context_str += rag_str
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_api.py::test_chat_includes_rag_context -v
```
Expected: PASS.

**Step 5: Full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all pass.

**Step 6: Commit**

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat(rag): augment Phil chat with semantic mail history (RAG)"
```

---

## Task 5: Frontend — API client + types

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`

**Step 1: Add KnowledgeResult type to types.ts**

Find the end of `types.ts` and add:

```typescript
export interface KnowledgeResult {
  id: string
  subject: string
  sender: string
  date: string
  kategorie: string
  summary: string
  score: number
}
```

**Step 2: Extend analyze() and add knowledgeSearch() in client.ts**

Find `analyze` in `client.ts` and replace:

```typescript
analyze: (email_text: string, meta?: { mail_id: string; subject: string; sender: string; date: string }) =>
  post<{ kategorie: string; priorität: number; zusammenfassung: string; empfohlene_aktion: string; stimmung?: number }>(
    '/api/analyze', { email_text, ...meta }),
```

Add after the existing methods:

```typescript
knowledgeSearch: (q: string, n = 3) =>
  get<{ results: KnowledgeResult[] }>(`/api/knowledge/search?q=${encodeURIComponent(q)}&n=${n}`),
```

Also add `KnowledgeResult` to the import in files that use it.

**Step 3: Build to verify no TypeScript errors**

```bash
cd frontend && npm run build
```
Expected: no TypeScript errors, build succeeds.

**Step 4: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts
git commit -m "feat(rag): add KnowledgeResult type + knowledgeSearch API call"
```

---

## Task 6: Frontend — Pass mail metadata to analyze

**Files:**
- Modify: `frontend/src/hooks/useDataLoader.ts`

**Step 1: Pass mail_id, subject, sender, date to api.analyze()**

Find the `api.analyze(text)` call in `useDataLoader.ts` (line ~40) and replace:

```typescript
const result = await api.analyze(text, {
  mail_id: mail.id,
  subject: mail.subject ?? '',
  sender: mail.sender ?? '',
  date: mail.datetime_received?.slice(0, 10) ?? '',
})
```

**Step 2: Build to verify**

```bash
cd frontend && npm run build
```
Expected: builds cleanly.

**Step 3: Commit**

```bash
git add frontend/src/hooks/useDataLoader.ts
git commit -m "feat(rag): pass mail metadata to /api/analyze for indexing"
```

---

## Task 7: Frontend — PhilPanel shows RAG sources

**Files:**
- Modify: `frontend/src/components/Phil/PhilPanel.tsx`
- Modify: `frontend/src/components/Phil/PhilPanel.module.css`

**Step 1: Add state and retrieval to PhilPanel.tsx**

Add state near the other `useState` declarations:

```typescript
const [ragResults, setRagResults] = useState<KnowledgeResult[]>([])
const [ragQuery, setRagQuery] = useState('')
```

Import the type:
```typescript
import type { KnowledgeResult } from '../../api/types'
```

In `send()`, after `setInput('')` and before `setStreaming(true)`, add a non-blocking knowledge search:

```typescript
// Fetch RAG sources in parallel (non-blocking — don't await)
setRagResults([])
setRagQuery(text)
api.knowledgeSearch(text, 3)
  .then(({ results }) => setRagResults(results))
  .catch(() => {})
```

**Step 2: Add sources UI below the message list**

After the `messages.map(...)` block and before `<div ref={messagesEndRef} />`, add:

```tsx
{ragResults.length > 0 && (
  <details className={styles.ragSources}>
    <summary className={styles.ragSummary}>
      📚 {ragResults.length} ähnliche frühere Mail{ragResults.length > 1 ? 's' : ''} gefunden
    </summary>
    {ragResults.map((r) => (
      <div key={r.id} className={styles.ragItem}>
        <span className={styles.ragScore}>{Math.round(r.score * 100)}%</span>
        <div className={styles.ragMeta}>
          <span className={styles.ragSubject}>{r.subject}</span>
          <span className={styles.ragSender}>{r.sender} · {r.date}</span>
          <span className={styles.ragSummaryText}>{r.summary}</span>
        </div>
      </div>
    ))}
  </details>
)}
```

**Step 3: Add CSS to PhilPanel.module.css**

```css
/* ── RAG Sources ──────────────────────────────────────────────────────────── */
.ragSources {
  margin: .25rem .875rem .5rem;
  border: 1px solid var(--content-border);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  background: var(--content-bg);
}
.ragSummary {
  padding: .4rem .7rem;
  cursor: pointer;
  color: #6B7280;
  font-weight: 600;
  list-style: none;
}
.ragSummary::-webkit-details-marker { display: none; }
.ragSummary:hover { color: var(--amber-dark); }
.ragItem {
  display: flex; gap: .5rem; align-items: flex-start;
  padding: .4rem .7rem;
  border-top: 1px solid var(--content-border);
}
.ragScore {
  font-size: .7rem; font-weight: 700;
  color: white; background: var(--amber);
  border-radius: 4px; padding: 1px 5px;
  flex-shrink: 0; margin-top: 1px;
}
.ragMeta { display: flex; flex-direction: column; gap: .1rem; min-width: 0; }
.ragSubject { font-weight: 600; color: #18181B; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ragSender { color: #9CA3AF; }
.ragSummaryText { color: #6B7280; font-style: italic; }
```

**Step 4: Build to verify**

```bash
cd frontend && npm run build
```
Expected: builds cleanly, no TypeScript errors.

**Step 5: Full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all pass.

**Step 6: Commit**

```bash
git add frontend/src/components/Phil/PhilPanel.tsx frontend/src/components/Phil/PhilPanel.module.css frontend/src/api/types.ts
git commit -m "feat(rag): Phil shows semantically retrieved mail sources"
```

---

## Verification

```bash
# 1. All tests green
cd UC2_Nachrichten_Triage/webapp
python -m pytest tests/ -v  # all pass

# 2. Backend starts clean
uvicorn backend.main:app --port 8001 --reload

# 3. Manual smoke test:
# - Log in, wait for mail triage to run
# - data/chroma/ directory appears and grows
# - Open Phil, type: "Gab es schon Mails über [Thema das du weißt]?"
# - Phil antwortet mit Kontext aus der Mailhistorie
# - Unter der Antwort erscheint "📚 2 ähnliche frühere Mails gefunden"
# - Aufklappen zeigt Betreff, Absender, Datum, Zusammenfassung, Relevanzscore

# 4. Search endpoint direkt testen (im Browser nach Login):
# GET http://localhost:8001/api/knowledge/search?q=Projekt  → JSON mit results
```

## RAG Pipeline — Überblick für die Lehre

```
Mail eingeht
    │
    ▼
POST /api/analyze  ──►  Claude (Triage)  ──►  { kategorie, zusammenfassung, … }
    │                                               │
    │                                               ▼
    └──────────────────────────────►  OpenAI text-embedding-3-small
                                                    │
                                                    ▼
                                           ChromaDB (./data/chroma/)
                                           [Vektorindex aller triagierter Mails]

Phil-Frage: "Was war mit dem DFG-Antrag?"
    │
    ▼
OpenAI text-embedding-3-small (Query-Embedding)
    │
    ▼
ChromaDB cosine similarity search  ──►  Top-3 ähnlichste Mails
    │
    ▼
"=== MAILHISTORIE ===" + aktuelle Situation + Nutzerfrage
    │
    ▼
Claude claude-opus-4-6 (antwortet mit historischem Kontext)
    │
    ▼
Phil-Antwort + "📚 Gefundene Quellen" im UI
```
