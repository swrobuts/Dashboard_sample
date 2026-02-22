# Attachments + Ontologie — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add PDF/DOCX attachment extraction + ChromaDB indexing, and a RDFLib mail-domain ontology with SPARQL-based chat enrichment to the PHIL app.

**Architecture:** Attachments arrive as base64 in `POST /api/analyze`, are decoded → text-extracted (pdfplumber/python-docx) → summarised by Claude → indexed in ChromaDB (`doc_type=attachment`). In the same request a second Claude call extracts structured entities (persons, projects, deadlines, action items) that are persisted as RDF triples in `data/ontology.ttl` via RDFLib. Phil's `/api/chat` acquires two new context blocks: `=== MAILHISTORIE ===` (already live) and `=== WISSENSGRAPH ===` (new, from SPARQL).

**Tech Stack:** FastAPI, pdfplumber ≥ 0.11, python-docx ≥ 1.1, rdflib ≥ 7.0, ChromaDB ≥ 0.5, Anthropic claude-opus-4-6, React/TypeScript/Vite, pytest-mock

---

## Prerequisites

```bash
# Working directory
cd UC2_Nachrichten_Triage/webapp

# Baseline: all existing tests must stay green
python -m pytest tests/ -v   # expect ~30 tests passing
```

---

## Task 1 — backend/attachment_extractor.py

**Files:**
- Create: `backend/attachment_extractor.py`
- Create: `tests/test_attachment_extractor.py`
- Modify: `backend/requirements.txt` (add two deps)

### Step 1 — Add dependencies to requirements.txt

Append to `backend/requirements.txt`:
```
pdfplumber>=0.11
python-docx>=1.1
```

Install locally:
```bash
pip install "pdfplumber>=0.11" "python-docx>=1.1"
```

### Step 2 — Write the failing tests

Create `tests/test_attachment_extractor.py`:

```python
# tests/test_attachment_extractor.py
import pytest
from backend.attachment_extractor import extract_text


def test_extract_pdf_returns_text(mocker):
    """_extract_pdf joins non-None page texts with newlines."""
    import pdfplumber  # ensure module is in sys.modules so patch works
    mock_page1 = mocker.MagicMock()
    mock_page1.extract_text.return_value = "Seite 1"
    mock_page2 = mocker.MagicMock()
    mock_page2.extract_text.return_value = None   # blank page — must be excluded
    mock_ctx = mocker.MagicMock()
    mock_ctx.__enter__ = mocker.MagicMock(return_value=mock_ctx)
    mock_ctx.__exit__ = mocker.MagicMock(return_value=False)
    mock_ctx.pages = [mock_page1, mock_page2]
    mocker.patch("pdfplumber.open", return_value=mock_ctx)

    result = extract_text(b"fake-pdf", "application/pdf")
    assert result == "Seite 1"


def test_extract_docx_returns_text(mocker):
    """_extract_docx joins non-empty paragraphs with newlines."""
    import docx  # ensure in sys.modules
    mock_p1 = mocker.MagicMock(); mock_p1.text = "Erster Absatz"
    mock_p2 = mocker.MagicMock(); mock_p2.text = ""   # blank — must be excluded
    mock_p3 = mocker.MagicMock(); mock_p3.text = "Dritter Absatz"
    mock_doc = mocker.MagicMock()
    mock_doc.paragraphs = [mock_p1, mock_p2, mock_p3]
    mocker.patch("docx.Document", return_value=mock_doc)

    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    result = extract_text(b"fake-docx", mime)
    assert result == "Erster Absatz\nDritter Absatz"


def test_extract_msword_also_supported(mocker):
    """application/msword is also handled as DOCX."""
    import docx
    mock_doc = mocker.MagicMock()
    mock_doc.paragraphs = []
    mocker.patch("docx.Document", return_value=mock_doc)

    result = extract_text(b"fake", "application/msword")
    assert result == ""   # no paragraphs → empty, but no exception


def test_extract_unknown_mime_returns_empty():
    """Unsupported MIME types return empty string without error."""
    assert extract_text(b"data", "image/jpeg") == ""
    assert extract_text(b"data", "text/plain") == ""
```

### Step 3 — Run tests to confirm FAIL

```bash
python -m pytest tests/test_attachment_extractor.py -v
# Expected: ImportError / ModuleNotFoundError — file doesn't exist yet
```

### Step 4 — Implement backend/attachment_extractor.py

Create `backend/attachment_extractor.py`:

```python
# backend/attachment_extractor.py
from __future__ import annotations
import io

DOCX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


def extract_text(data: bytes, mime_type: str) -> str:
    """Return plain text from PDF or DOCX bytes. Returns '' for unsupported types."""
    if mime_type == "application/pdf":
        return _extract_pdf(data)
    if mime_type in DOCX_MIME_TYPES:
        return _extract_docx(data)
    return ""


def _extract_pdf(data: bytes) -> str:
    import pdfplumber
    parts = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


def _extract_docx(data: bytes) -> str:
    import docx
    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
```

### Step 5 — Run tests to confirm PASS

```bash
python -m pytest tests/test_attachment_extractor.py -v
# Expected: 4 tests PASSED
```

### Step 6 — Commit

```bash
git add backend/attachment_extractor.py tests/test_attachment_extractor.py backend/requirements.txt
git commit -m "feat(attachments): PDF/DOCX text extractor + tests"
```

---

## Task 2 — backend/ontology_store.py

**Files:**
- Create: `backend/ontology_store.py`
- Create: `tests/test_ontology_store.py`
- Modify: `backend/requirements.txt` (add rdflib)

### Step 1 — Add rdflib to requirements.txt

Append:
```
rdflib>=7.0
```

Install:
```bash
pip install "rdflib>=7.0"
```

### Step 2 — Write the failing tests

Create `tests/test_ontology_store.py`:

```python
# tests/test_ontology_store.py
import pytest
from backend.ontology_store import OntologyStore


@pytest.fixture
def store(tmp_path):
    return OntologyStore(ttl_path=tmp_path / "ontology.ttl")


def test_add_mail_and_query_entities(store):
    """add_mail_triples persists persons, projects, tasks, deadlines."""
    store.add_mail_triples(
        mail_id="mail-001",
        sender_name="Prof. Müller",
        sender_email="mueller@hdm.de",
        subject="KI-Modul Besprechung",
        entities={
            "persons": ["Dr. Schmidt"],
            "projects": ["KI-Modul SS26"],
            "deadlines": ["2026-03-15"],
            "action_items": ["Gutachten einreichen"],
        },
    )
    ents = store.get_all_entities()
    names = [e["name"] for e in ents["persons"]]
    assert "Prof. Müller" in names
    assert "Dr. Schmidt" in names
    assert any(p["description"] == "KI-Modul SS26" for p in ents["projects"])
    assert any(t["description"] == "Gutachten einreichen" for t in ents["tasks"])
    assert any(d["date"] == "2026-03-15" for d in ents["deadlines"])


def test_get_context_for_chat_contains_wissensgraph(store):
    store.add_mail_triples(
        mail_id="mail-x",
        sender_name="Alice",
        sender_email="alice@test.de",
        subject="Test",
        entities={"persons": [], "projects": ["ProjektX"], "deadlines": [], "action_items": []},
    )
    ctx = store.get_context_for_chat("ProjektX")
    assert "WISSENSGRAPH" in ctx
    assert "ProjektX" in ctx


def test_empty_store_returns_empty_context(store):
    assert store.get_context_for_chat("anything") == ""


def test_persist_and_reload(tmp_path):
    path = tmp_path / "onto.ttl"
    s1 = OntologyStore(ttl_path=path)
    s1.add_mail_triples(
        "m1", "Bob", "bob@x.de", "Subject",
        {"persons": [], "projects": ["ProjX"], "deadlines": [], "action_items": []},
    )
    s2 = OntologyStore(ttl_path=path)   # fresh instance from disk
    ents = s2.get_all_entities()
    assert any(p["description"] == "ProjX" for p in ents["projects"])
```

### Step 3 — Run to confirm FAIL

```bash
python -m pytest tests/test_ontology_store.py -v
# Expected: ImportError — file doesn't exist yet
```

### Step 4 — Implement backend/ontology_store.py

Create `backend/ontology_store.py`:

```python
# backend/ontology_store.py
from __future__ import annotations
import logging
import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF

PHIL = Namespace("http://hdm-stuttgart.de/phil/ont/")
_DEFAULT_TTL = Path("./data/ontology.ttl")


def _slug(text: str) -> str:
    """Sanitise text to a URI-safe slug (max 64 chars)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", text.strip().lower())[:64]


class OntologyStore:
    def __init__(self, ttl_path: str | Path = _DEFAULT_TTL):
        self._path = Path(ttl_path)
        self._g = Graph()
        self._g.bind("phil", PHIL)
        if self._path.exists():
            self._g.parse(str(self._path), format="turtle")

    # ── Public API ─────────────────────────────────────────────────────────

    def add_mail_triples(
        self,
        mail_id: str,
        sender_name: str,
        sender_email: str,
        subject: str,
        entities: dict,
    ) -> None:
        """
        Persist mail + extracted entities as RDF triples.

        entities = {
          "persons": [...],
          "projects": [...],
          "deadlines": [...],    # strings (dates or descriptions)
          "action_items": [...],
        }
        """
        g = self._g
        mail_uri = PHIL[f"mail-{_slug(mail_id)}"]
        g.add((mail_uri, RDF.type, PHIL.Mail))
        g.add((mail_uri, PHIL.subject, Literal(subject)))

        # Sender
        sender_uri = PHIL[f"person-{_slug(sender_email or sender_name)}"]
        g.add((sender_uri, RDF.type, PHIL.Person))
        g.add((sender_uri, PHIL.name, Literal(sender_name)))
        if sender_email:
            g.add((sender_uri, PHIL.email, Literal(sender_email)))
        g.add((mail_uri, PHIL.sentBy, sender_uri))

        for name in entities.get("persons", []):
            p_uri = PHIL[f"person-{_slug(name)}"]
            g.add((p_uri, RDF.type, PHIL.Person))
            g.add((p_uri, PHIL.name, Literal(name)))
            g.add((mail_uri, PHIL.mentionsPerson, p_uri))

        for proj in entities.get("projects", []):
            proj_uri = PHIL[f"projekt-{_slug(proj)}"]
            g.add((proj_uri, RDF.type, PHIL.Projekt))
            g.add((proj_uri, PHIL.description, Literal(proj)))
            g.add((mail_uri, PHIL.relatedTo, proj_uri))

        for dl in entities.get("deadlines", []):
            dl_uri = PHIL[f"termin-{_slug(dl)}"]
            g.add((dl_uri, RDF.type, PHIL.Termin))
            g.add((dl_uri, PHIL.date, Literal(dl)))
            g.add((mail_uri, PHIL.hasDeadline, dl_uri))

        for action in entities.get("action_items", []):
            act_uri = PHIL[f"aufgabe-{_slug(action)}"]
            g.add((act_uri, RDF.type, PHIL.Aufgabe))
            g.add((act_uri, PHIL.description, Literal(action)))
            g.add((mail_uri, PHIL.requiresAction, act_uri))

        self._save()

    def get_all_entities(self) -> dict:
        """Return all entities for the /api/ontology/entities endpoint."""
        return {
            "persons": [{"name": n, "mail_count": c} for n, c in self._query_persons()],
            "projects": [{"description": p} for p in self._query_projects()],
            "tasks": [{"description": t} for t in self._query_tasks()],
            "deadlines": [{"date": d} for d in self._query_deadlines()],
        }

    def get_context_for_chat(self, query: str) -> str:
        """Build =WISSENSGRAPH= context block for Phil's chat prompt."""
        persons = self._query_persons()
        projects = self._query_projects()
        tasks = self._query_tasks()
        if not persons and not projects and not tasks:
            return ""
        lines = ["\n=== WISSENSGRAPH (strukturierte Verbindungen) ==="]
        if persons:
            lines.append(
                "  Personen: " + ", ".join(f"{n} ({c} Mails)" for n, c in persons[:5])
            )
        if projects:
            lines.append("  Projekte: " + ", ".join(projects[:5]))
        if tasks:
            lines.append("  Offene Aufgaben: " + "; ".join(tasks[:3]))
        return "\n".join(lines)

    def get_triples_for_mail(self, mail_id: str) -> list[dict]:
        """Return all triples where subject is the given mail URI."""
        mail_uri = PHIL[f"mail-{_slug(mail_id)}"]
        return [
            {"s": str(s), "p": str(p), "o": str(o)}
            for s, p, o in self._g.triples((mail_uri, None, None))
        ]

    # ── SPARQL helpers ─────────────────────────────────────────────────────

    def _query_persons(self) -> list[tuple[str, int]]:
        q = """
        PREFIX phil: <http://hdm-stuttgart.de/phil/ont/>
        SELECT ?name (COUNT(?mail) AS ?cnt)
        WHERE {
            ?mail a phil:Mail .
            { ?mail phil:mentionsPerson ?p } UNION { ?mail phil:sentBy ?p }
            ?p phil:name ?name .
        }
        GROUP BY ?name
        ORDER BY DESC(?cnt)
        """
        try:
            return [(str(row.name), int(row.cnt)) for row in self._g.query(q)]
        except Exception as exc:
            logging.warning(f"[Ontology] SPARQL persons: {exc}")
            return []

    def _query_projects(self) -> list[str]:
        q = """
        PREFIX phil: <http://hdm-stuttgart.de/phil/ont/>
        SELECT DISTINCT ?desc WHERE { ?p a phil:Projekt ; phil:description ?desc . }
        """
        try:
            return [str(row.desc) for row in self._g.query(q)]
        except Exception as exc:
            logging.warning(f"[Ontology] SPARQL projects: {exc}")
            return []

    def _query_tasks(self) -> list[str]:
        q = """
        PREFIX phil: <http://hdm-stuttgart.de/phil/ont/>
        SELECT DISTINCT ?desc WHERE { ?a a phil:Aufgabe ; phil:description ?desc . }
        """
        try:
            return [str(row.desc) for row in self._g.query(q)]
        except Exception as exc:
            logging.warning(f"[Ontology] SPARQL tasks: {exc}")
            return []

    def _query_deadlines(self) -> list[str]:
        q = """
        PREFIX phil: <http://hdm-stuttgart.de/phil/ont/>
        SELECT DISTINCT ?date WHERE { ?t a phil:Termin ; phil:date ?date . }
        ORDER BY ?date
        """
        try:
            return [str(row.date) for row in self._g.query(q)]
        except Exception as exc:
            logging.warning(f"[Ontology] SPARQL deadlines: {exc}")
            return []

    # ── Persistence ────────────────────────────────────────────────────────

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._g.serialize(str(self._path), format="turtle")
```

### Step 5 — Run to confirm PASS

```bash
python -m pytest tests/test_ontology_store.py -v
# Expected: 4 tests PASSED
```

### Step 6 — Commit

```bash
git add backend/ontology_store.py tests/test_ontology_store.py backend/requirements.txt
git commit -m "feat(ontology): RDFLib OntologyStore + SPARQL queries + tests"
```

---

## Task 3 — backend/knowledge_store.py: index_attachment()

**Files:**
- Modify: `backend/knowledge_store.py`
- Modify: `tests/test_knowledge_store.py`

### Step 1 — Write the failing test

Append to `tests/test_knowledge_store.py`:

```python
def test_index_attachment_and_search(store):
    """index_attachment stores into same collection with doc_type=attachment."""
    store.index_attachment(
        mail_id="mail-42",
        filename="bericht.pdf",
        summary="Jahresbericht 2025 des Instituts.",
        body_snippet="Das Jahr 2025 war geprägt von Wachstum.",
    )
    # search returns the attachment (same collection)
    results = store.search("Jahresbericht Institut", n_results=1)
    assert len(results) == 1
    assert results[0]["id"] == "att-mail-42-bericht.pdf"


def test_index_attachment_upsert_idempotent(store):
    for _ in range(2):
        store.index_attachment("mid", "doc.docx", "Summary", "Body text")
    assert store.collection.count() == 1
```

### Step 2 — Run to confirm FAIL

```bash
python -m pytest tests/test_knowledge_store.py::test_index_attachment_and_search -v
# Expected: AttributeError: 'KnowledgeStore' object has no attribute 'index_attachment'
```

### Step 3 — Add index_attachment() to KnowledgeStore

Append the method to `backend/knowledge_store.py` (inside the class, after `search()`):

```python
    def index_attachment(
        self,
        mail_id: str,
        filename: str,
        summary: str,
        body_snippet: str,
    ) -> None:
        """Embed and upsert an attachment into the mail collection.

        Uses the same ChromaDB collection as mails.
        ID format: ``att-<mail_id>-<filename>``.
        Metadata includes ``doc_type=attachment`` for later filtering.
        """
        document = (
            f"Dateiname: {filename}\n"
            f"Zusammenfassung: {summary}\n"
            f"{body_snippet[:self._BODY_LIMIT]}"
        )
        att_id = f"att-{mail_id}-{filename}"
        self.collection.upsert(
            ids=[att_id],
            documents=[document],
            metadatas=[{
                "mail_id": mail_id,
                "filename": filename,
                "summary": summary,
                "doc_type": "attachment",
            }],
        )
```

### Step 4 — Run to confirm PASS

```bash
python -m pytest tests/test_knowledge_store.py -v
# Expected: 5 tests PASSED (3 existing + 2 new)
```

### Step 5 — Commit

```bash
git add backend/knowledge_store.py tests/test_knowledge_store.py
git commit -m "feat(rag): KnowledgeStore.index_attachment() + tests"
```

---

## Task 4 — backend/main.py: AttachmentIn + attachment pipeline in analyze()

**Files:**
- Modify: `backend/main.py`
- Modify: `tests/test_api.py`

### Step 1 — Write the failing tests

Append to `tests/test_api.py`:

```python
import base64

# ── Attachment Tests ───────────────────────────────────────────────────────

def test_analyze_with_attachment_calls_extract_and_index(mocker):
    """analyze() extracts text from PDF attachment and indexes it."""
    mock_triage_resp = mocker.MagicMock()
    mock_triage_resp.content[0].text = json.dumps({
        "kategorie": "Aktion nötig", "priorität": 2,
        "zusammenfassung": "Mit Anhang.", "empfohlene_aktion": "Lesen.",
    })
    mock_summary_resp = mocker.MagicMock()
    mock_summary_resp.content[0].text = "Kurze Zusammenfassung des Anhangs."

    # Claude is called twice: triage + attachment summary
    mocker.patch(
        "backend.main.anthropic_client.messages.create",
        side_effect=[mock_triage_resp, mock_summary_resp],
    )
    mocker.patch("backend.attachment_extractor._extract_pdf", return_value="PDF content here")
    mock_index = mocker.patch("backend.main.knowledge_store")
    mock_index.index_mail = mocker.MagicMock()
    mock_index.index_attachment = mocker.MagicMock()

    fake_pdf = base64.b64encode(b"%PDF-1.4 fake").decode()
    client = get_client()
    r = client.post("/api/analyze", json={
        "email_text": "Bitte Anhang beachten.",
        "mail_id": "m-1",
        "subject": "Mit Anhang",
        "sender": "test@test.de",
        "date": "2026-02-22",
        "attachments": [{"filename": "report.pdf", "mime_type": "application/pdf", "data_b64": fake_pdf}],
    })
    assert r.status_code == 200
    mock_index.index_attachment.assert_called_once()
    call_kwargs = mock_index.index_attachment.call_args.kwargs
    assert call_kwargs["filename"] == "report.pdf"
    assert call_kwargs["mail_id"] == "m-1"


def test_analyze_without_attachments_unchanged(mocker):
    """analyze() with empty attachments list behaves as before."""
    mock_resp = mocker.MagicMock()
    mock_resp.content[0].text = json.dumps({
        "kategorie": "Nur Info", "priorität": 3,
        "zusammenfassung": "Ohne Anhang.", "empfohlene_aktion": "Zur Kenntnis.",
    })
    mocker.patch("backend.main.anthropic_client.messages.create", return_value=mock_resp)
    mock_index = mocker.patch("backend.main.knowledge_store")
    mock_index.index_attachment = mocker.MagicMock()

    client = get_client()
    r = client.post("/api/analyze", json={"email_text": "Keine Anhänge hier.", "attachments": []})
    assert r.status_code == 200
    mock_index.index_attachment.assert_not_called()
```

### Step 2 — Run to confirm FAIL

```bash
python -m pytest tests/test_api.py::test_analyze_with_attachment_calls_extract_and_index -v
# Expected: FAIL — ValidationError: attachments field not found
```

### Step 3 — Implement in main.py

**3a) Add AttachmentIn model** (after the `_strip_fences` function, before `AnalyzeRequest`):

```python
class AttachmentIn(BaseModel):
    filename: str
    mime_type: str
    data_b64: str   # base64-encoded bytes
```

**3b) Add `attachments` field to `AnalyzeRequest`**:

```python
class AnalyzeRequest(BaseModel):
    email_text: str
    mail_id: str | None = None
    subject: str = ""
    sender: str = ""
    date: str = ""
    attachments: list[AttachmentIn] = []

    @field_validator("email_text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("email_text darf nicht leer sein")
        return v
```

**3c) Add `_summarize_attachment()` helper** (after `_strip_fences`):

```python
def _summarize_attachment(filename: str, text: str) -> str:
    """Call Claude for a concise 3-sentence attachment summary."""
    prompt = (
        f"Fasse den folgenden Anhang '{filename}' in maximal 3 Sätzen zusammen:\n\n"
        f"{text[:3000]}"
    )
    try:
        resp = anthropic_client.messages.create(
            model="claude-opus-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as exc:
        logging.warning(f"[Attachment] Zusammenfassung fehlgeschlagen: {exc}")
        return ""
```

**3d) Add import** at the top of `main.py` (with other local imports):

```python
from backend.attachment_extractor import extract_text as extract_attachment_text
```

**3e) Modify `analyze()` function** — replace the entire function body with:

```python
@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    import base64

    # ── Attachment extraction ──────────────────────────────────────────
    attachment_snippets: list[str] = []
    attachments_to_index: list[tuple[AttachmentIn, str]] = []  # (att, full_text)

    for att in req.attachments:
        try:
            data = base64.b64decode(att.data_b64)
            text = extract_attachment_text(data, att.mime_type)
        except Exception as exc:
            logging.warning(f"[Attachment] Extraktion fehlgeschlagen {att.filename}: {exc}")
            continue
        if not text.strip():
            continue
        attachment_snippets.append(f"\n[Anhang: {att.filename}]\n{text[:2000]}")
        attachments_to_index.append((att, text))

    # ── Triage (with attachment context) ──────────────────────────────
    email_with_attachments = req.email_text
    if attachment_snippets:
        email_with_attachments += "\n\n" + "\n".join(attachment_snippets)

    prompt = COSTAR_PROMPT.format(email_text=email_with_attachments)
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

    # ── Index mail in ChromaDB (non-fatal) ─────────────────────────────
    if req.mail_id and knowledge_store is not None:
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
            logging.warning(f"[RAG] Indexierung fehlgeschlagen: {exc}")

    # ── Summarise + index attachments (non-fatal) ──────────────────────
    for att, att_text in attachments_to_index:
        try:
            att_summary = _summarize_attachment(att.filename, att_text)
            if knowledge_store is not None:
                knowledge_store.index_attachment(
                    mail_id=req.mail_id or "unknown",
                    filename=att.filename,
                    summary=att_summary,
                    body_snippet=att_text,
                )
        except Exception as exc:
            logging.warning(f"[Attachment] Indexierung fehlgeschlagen {att.filename}: {exc}")

    return result
```

### Step 4 — Run to confirm PASS

```bash
python -m pytest tests/test_api.py::test_analyze_with_attachment_calls_extract_and_index tests/test_api.py::test_analyze_without_attachments_unchanged -v
# Expected: 2 tests PASSED

python -m pytest tests/ -v
# Expected: all ~32 tests PASSED
```

### Step 5 — Commit

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat(attachments): AttachmentIn model, extraction pipeline, ChromaDB indexing"
```

---

## Task 5 — backend/main.py: entity extraction + ontology_store singleton

**Files:**
- Modify: `backend/main.py`
- Modify: `tests/test_api.py`

### Step 1 — Write the failing tests

Append to `tests/test_api.py`:

```python
# ── Ontology Tests ──────────────────────────────────────────────────────────

def test_ontology_entity_extraction_after_analyze(mocker):
    """analyze() calls entity extraction and adds ontology triples when mail_id given."""
    mock_triage = mocker.MagicMock()
    mock_triage.content[0].text = json.dumps({
        "kategorie": "VIP", "priorität": 1,
        "zusammenfassung": "Wichtige Mail.", "empfohlene_aktion": "Antworten.",
    })
    mock_entities = mocker.MagicMock()
    mock_entities.content[0].text = json.dumps({
        "persons": ["Prof. Test"],
        "projects": ["Testprojekt"],
        "deadlines": ["2026-03-01"],
        "action_items": ["Antwort senden"],
    })
    mocker.patch(
        "backend.main.anthropic_client.messages.create",
        side_effect=[mock_triage, mock_entities],
    )
    mock_store = mocker.patch("backend.main.ontology_store")
    mock_store.add_mail_triples = mocker.MagicMock()

    client = get_client()
    r = client.post("/api/analyze", json={
        "email_text": "Mail von Prof. Test über Testprojekt.",
        "mail_id": "m-ont-1",
        "subject": "Testprojekt",
        "sender": "Prof. Test <test@hdm.de>",
        "date": "2026-02-22",
    })
    assert r.status_code == 200
    mock_store.add_mail_triples.assert_called_once()
    call_kw = mock_store.add_mail_triples.call_args.kwargs
    assert call_kw["mail_id"] == "m-ont-1"
    assert "Prof. Test" in call_kw["entities"]["persons"]


def test_ontology_skipped_when_no_mail_id(mocker):
    """analyze() does NOT call ontology when mail_id is missing."""
    mock_resp = mocker.MagicMock()
    mock_resp.content[0].text = json.dumps({
        "kategorie": "Nur Info", "priorität": 3,
        "zusammenfassung": "FYI.", "empfohlene_aktion": "Ignorieren.",
    })
    mocker.patch("backend.main.anthropic_client.messages.create", return_value=mock_resp)
    mock_store = mocker.patch("backend.main.ontology_store")
    mock_store.add_mail_triples = mocker.MagicMock()

    client = get_client()
    r = client.post("/api/analyze", json={"email_text": "Kein mail_id hier."})
    assert r.status_code == 200
    mock_store.add_mail_triples.assert_not_called()
```

### Step 2 — Run to confirm FAIL

```bash
python -m pytest tests/test_api.py::test_ontology_entity_extraction_after_analyze -v
# Expected: FAIL — ontology_store not yet defined in main.py
```

### Step 3 — Implement in main.py

**3a) Add imports** at top of `main.py` (with other local imports):

```python
from backend.ontology_store import OntologyStore
```

**3b) Add singleton** (immediately after the `knowledge_store` singleton block):

```python
try:
    ontology_store = OntologyStore()
except Exception as e:
    logging.warning(f"[Ontology] OntologyStore deaktiviert: {type(e).__name__}: {e}")
    ontology_store = None
```

**3c) Add `_parse_sender()` helper** (after `_strip_fences`):

```python
def _parse_sender(sender: str) -> tuple[str, str]:
    """Extract (name, email) from 'Name <email>' or plain email string."""
    m = re.match(r'^["\']?([^<"\']+?)["\']?\s*<([^>]+)>', sender.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    if "@" in sender:
        return sender.strip(), sender.strip()
    return sender.strip(), ""
```

**3d) Add `_extract_entities()` helper** (after `_summarize_attachment`):

```python
def _extract_entities(mail_text: str) -> dict:
    """Call Claude to extract structured entities from mail text.

    Returns dict with keys: persons, projects, deadlines, action_items.
    Returns empty lists on any error — never raises.
    """
    _EMPTY = {"persons": [], "projects": [], "deadlines": [], "action_items": []}
    prompt = (
        "Extrahiere aus der folgenden E-Mail strukturierte Entitäten als JSON.\n"
        "Antworte NUR mit validem JSON — kein Text davor oder danach:\n"
        "{\n"
        '  "persons": ["vollständige Namen erwähnter Personen (keine E-Mail-Adressen)"],\n'
        '  "projects": ["erwähnte Projekte, Anträge, Vorhaben (leer wenn keine)"],\n'
        '  "deadlines": ["Daten im Format YYYY-MM-DD oder kurze Beschreibung (leer wenn keine)"],\n'
        '  "action_items": ["konkrete Aufgaben oder Anforderungen (leer wenn keine)"]\n'
        "}\n\n"
        f"E-Mail:\n{mail_text[:2000]}"
    )
    try:
        resp = anthropic_client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_fences(resp.content[0].text)
        data = json.loads(raw)
        # Validate structure — ensure all keys exist
        return {k: data.get(k, []) for k in _EMPTY}
    except Exception as exc:
        logging.warning(f"[Ontology] Entity-Extraktion fehlgeschlagen: {exc}")
        return _EMPTY
```

**3e) Add ontology call inside `analyze()`** — append after the attachment indexing block (before `return result`):

```python
    # ── Entity extraction + ontology triples (non-fatal) ──────────────
    if req.mail_id and ontology_store is not None:
        try:
            entities = _extract_entities(req.email_text)
            sender_name, sender_email = _parse_sender(req.sender)
            ontology_store.add_mail_triples(
                mail_id=req.mail_id,
                sender_name=sender_name,
                sender_email=sender_email,
                subject=req.subject,
                entities=entities,
            )
        except Exception as exc:
            logging.warning(f"[Ontology] Tripel-Erstellung fehlgeschlagen: {exc}")
```

### Step 4 — Run to confirm PASS

```bash
python -m pytest tests/test_api.py::test_ontology_entity_extraction_after_analyze tests/test_api.py::test_ontology_skipped_when_no_mail_id -v
# Expected: 2 PASSED

python -m pytest tests/ -v
# Expected: all ~34 tests PASSED
```

### Step 5 — Commit

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat(ontology): entity extraction + OntologyStore singleton integrated into analyze()"
```

---

## Task 6 — backend/main.py: ontology endpoints + WISSENSGRAPH in chat()

**Files:**
- Modify: `backend/main.py`
- Modify: `tests/test_api.py`

### Step 1 — Write the failing tests

Append to `tests/test_api.py`:

```python
def test_ontology_entities_requires_session():
    client = get_client()
    r = client.get("/api/ontology/entities")
    assert r.status_code == 401


def test_ontology_search_requires_session():
    client = get_client()
    r = client.get("/api/ontology/search?q=Mueller")
    assert r.status_code == 401


def test_ontology_entities_returns_structure(mocker):
    """GET /api/ontology/entities returns dict with persons/projects/tasks/deadlines."""
    client = get_client()
    _login(client, mocker)
    mock_store = mocker.patch("backend.main.ontology_store")
    mock_store.get_all_entities.return_value = {
        "persons": [{"name": "Alice", "mail_count": 2}],
        "projects": [],
        "tasks": [],
        "deadlines": [],
    }
    r = client.get("/api/ontology/entities")
    assert r.status_code == 200
    data = r.json()
    assert "persons" in data
    assert data["persons"][0]["name"] == "Alice"


def test_chat_includes_graph_context(mocker):
    """POST /api/chat appends WISSENSGRAPH block when ontology_store returns data."""
    client = get_client()
    _login(client, mocker)

    mocker.patch("backend.main.fetch_emails_imap", return_value=[])
    mocker.patch("backend.main.fetch_google_calendar", return_value=[])
    mocker.patch("backend.main.fetch_tasks", return_value=[])
    mocker.patch("backend.main._build_rag_context", return_value="")
    mocker.patch(
        "backend.main._build_graph_context",
        return_value="\n=== WISSENSGRAPH ===\n  Personen: Alice (3 Mails)",
    )

    captured_msgs = []

    def fake_stream_cm(**kwargs):
        captured_msgs.extend(kwargs.get("messages", []))
        class FakeStream:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            @property
            def text_stream(self):
                yield "Antwort von PHIL."
        return FakeStream()

    mocker.patch("backend.main.anthropic_client.messages.stream", side_effect=fake_stream_cm)

    r = client.post("/api/chat", json={"message": "Wer hat mir geschrieben?", "include_context": True})
    assert r.status_code == 200
    assert len(captured_msgs) == 1
    assert "WISSENSGRAPH" in captured_msgs[0]["content"]
```

### Step 2 — Run to confirm FAIL

```bash
python -m pytest tests/test_api.py::test_ontology_entities_requires_session tests/test_api.py::test_chat_includes_graph_context -v
# Expected: FAIL — endpoints not yet defined
```

### Step 3 — Implement in main.py

**3a) Add `_build_graph_context()` helper** (after `_build_rag_context()`):

```python
def _build_graph_context(query: str) -> str:
    """Get structured knowledge graph context block from the ontology."""
    if ontology_store is None:
        return ""
    try:
        return ontology_store.get_context_for_chat(query)
    except Exception as exc:
        logging.warning(f"[Ontology] Graph-Kontext fehlgeschlagen: {exc}")
        return ""
```

**3b) Add WISSENSGRAPH block in `chat()`** — after the RAG block (after `if rag_str: context_str += rag_str`):

```python
        # Ontology: enrich with structured knowledge graph
        graph_str = _build_graph_context(req.message)
        if graph_str:
            context_str += graph_str
```

**3c) Add three ontology endpoints** (after the `/api/knowledge/search` endpoint):

```python
@app.get("/api/ontology/entities")
def get_ontology_entities(session_id: str | None = Cookie(default=None)):
    _get_session(session_id)
    if ontology_store is None:
        return {"persons": [], "projects": [], "tasks": [], "deadlines": []}
    return ontology_store.get_all_entities()


@app.get("/api/ontology/search")
def get_ontology_search(
    q: str = "",
    session_id: str | None = Cookie(default=None),
):
    _get_session(session_id)
    if ontology_store is None or not q.strip():
        return {"context": ""}
    return {"context": ontology_store.get_context_for_chat(q)}


@app.get("/api/ontology/graph")
def get_ontology_graph(
    mail_id: str = "",
    session_id: str | None = Cookie(default=None),
):
    _get_session(session_id)
    if ontology_store is None or not mail_id:
        return {"triples": []}
    return {"triples": ontology_store.get_triples_for_mail(mail_id)}
```

### Step 4 — Run to confirm PASS

```bash
python -m pytest tests/test_api.py -v -k "ontology or graph_context"
# Expected: all ontology-related tests PASSED

python -m pytest tests/ -v
# Expected: all ~38 tests PASSED
```

### Step 5 — Commit

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat(ontology): 3 ontology endpoints + WISSENSGRAPH block in chat()"
```

---

## Task 7 — Frontend: types, API client, PhilPanel WISSENSGRAPH section

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/Phil/PhilPanel.tsx`
- Modify: `frontend/src/components/Phil/PhilPanel.module.css`

This task has no automated pytest tests (frontend-only). Verify by running the dev server.

### Step 1 — Add types to frontend/src/api/types.ts

Append to `frontend/src/api/types.ts`:

```typescript
export interface AttachmentIn {
  filename: string
  mime_type: string
  data_b64: string
}

export interface OntologyEntities {
  persons: Array<{ name: string; mail_count: number }>
  projects: Array<{ description: string }>
  tasks: Array<{ description: string }>
  deadlines: Array<{ date: string }>
}
```

### Step 2 — Add API methods to frontend/src/api/client.ts

Import the new types at the top:

```typescript
import type { User, TriagedMail, CalendarItem, Task, TrainStation, TrainJourney, KnowledgeResult, OntologyEntities } from './types'
```

Add two methods to the `api` object (after `knowledgeSearch`):

```typescript
  // Ontology / Knowledge Graph
  ontologyEntities: () => get<OntologyEntities>('/api/ontology/entities'),
  ontologySearch: (q: string) =>
    get<{ context: string }>(`/api/ontology/search?q=${encodeURIComponent(q)}`),
```

### Step 3 — Add WISSENSGRAPH section to PhilPanel.tsx

**3a) Add import** at the top of `PhilPanel.tsx`:

```typescript
import type { KnowledgeResult, OntologyEntities } from '../../api/types'
```

(Replace the existing types import if needed.)

**3b) Add state** inside `PhilPanel` component (after `ragResults` state):

```typescript
const [ontologyData, setOntologyData] = useState<OntologyEntities | null>(null)
```

**3c) Load ontology data non-blocking in `send()`** — add after `api.knowledgeSearch(...)`:

```typescript
    api.ontologyEntities()
      .then(data => {
        const hasData = data.persons.length > 0 || data.projects.length > 0 || data.tasks.length > 0
        setOntologyData(hasData ? data : null)
      })
      .catch(() => {})
```

**3d) Add WISSENSGRAPH panel in JSX** — immediately after the closing `</details>` of the RAG sources section:

```tsx
      {ontologyData && (
        <details className={styles.graphSources}>
          <summary className={styles.ragSummary}>
            🧠 Wissensgraph
          </summary>
          {ontologyData.persons.length > 0 && (
            <div className={styles.ragItem}>
              <span className={styles.ragSender}>
                Personen: {ontologyData.persons.map(p => p.name).join(', ')}
              </span>
            </div>
          )}
          {ontologyData.projects.length > 0 && (
            <div className={styles.ragItem}>
              <span className={styles.ragSender}>
                Projekte: {ontologyData.projects.map(p => p.description).join(', ')}
              </span>
            </div>
          )}
          {ontologyData.tasks.length > 0 && (
            <div className={styles.ragItem}>
              <span className={styles.ragSummaryText}>
                Aufgaben: {ontologyData.tasks.map(t => t.description).join('; ')}
              </span>
            </div>
          )}
        </details>
      )}
```

### Step 4 — Add CSS to PhilPanel.module.css

Append to `frontend/src/components/Phil/PhilPanel.module.css`:

```css
.graphSources {
  border-top: 1px solid var(--border);
  padding: 6px 12px;
  font-size: 0.78rem;
  background: var(--surface);
}

.graphSources[open] {
  padding-bottom: 8px;
}
```

### Step 5 — Verify in dev server

```bash
cd UC2_Nachrichten_Triage/webapp
uvicorn backend.main:app --reload --port 8001 &
cd frontend && npm run dev
# Open http://localhost:5173
# Log in → triage a mail → open Phil chat → send a message
# Expected:
#   - RAG sources panel shows (📚) if mails indexed
#   - WISSENSGRAPH panel shows (🧠) after ontology has entries
#   - Phil's chat responses include WISSENSGRAPH context block
```

### Step 6 — Run full test suite one final time

```bash
cd UC2_Nachrichten_Triage/webapp
python -m pytest tests/ -v
# Expected: all ~38 tests PASSED
```

### Step 7 — Commit

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts \
        frontend/src/components/Phil/PhilPanel.tsx \
        frontend/src/components/Phil/PhilPanel.module.css
git commit -m "feat(frontend): OntologyEntities types, ontologySearch API, PhilPanel WISSENSGRAPH section"
```

---

## Verification Checklist

```bash
# ① All tests green
python -m pytest tests/ -v     # ~38 tests, 0 failures

# ② Dependencies installed
pip show pdfplumber python-docx rdflib   # all present

# ③ Attachment pipeline smoke-test (paste-mode)
# → Start app, paste a mail with a PDF URL attachment → check logs for "[Attachment]"

# ④ Ontology persists
ls data/ontology.ttl   # file created after first analyze() with mail_id

# ⑤ Ontology endpoint
curl -s -b session.txt http://localhost:8001/api/ontology/entities | python3 -m json.tool

# ⑥ Phil chat includes WISSENSGRAPH
# → Open Phil panel, send "Wer hat mir geschrieben?" → check Phil's response
#    for "WISSENSGRAPH" in the server logs (context_str)
```

---

## New Files Summary

| File | Purpose |
|---|---|
| `backend/attachment_extractor.py` | PDF/DOCX → plain text (pdfplumber, python-docx) |
| `backend/ontology_store.py` | RDFLib OntologyStore + SPARQL helpers |
| `tests/test_attachment_extractor.py` | 4 unit tests |
| `tests/test_ontology_store.py` | 4 unit tests |
| `data/ontology.ttl` | Auto-created: persistent RDF graph (Turtle) |

## Changed Files Summary

| File | Change |
|---|---|
| `backend/requirements.txt` | + pdfplumber, python-docx, rdflib |
| `backend/knowledge_store.py` | + `index_attachment()` method |
| `backend/main.py` | AttachmentIn model, `_summarize_attachment()`, `_extract_entities()`, `_parse_sender()`, `_build_graph_context()`, ontology singleton, attachment pipeline in `analyze()`, 3 new endpoints, WISSENSGRAPH in `chat()` |
| `frontend/src/api/types.ts` | + AttachmentIn, OntologyEntities |
| `frontend/src/api/client.ts` | + ontologyEntities(), ontologySearch() |
| `frontend/src/components/Phil/PhilPanel.tsx` | + ontologyData state, WISSENSGRAPH panel |
| `frontend/src/components/Phil/PhilPanel.module.css` | + .graphSources style |
| `tests/test_api.py` | + 6 new tests (attachment, ontology, chat) |
