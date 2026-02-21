# UC2 Web-App Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task.

**Goal:** Vollständige Web-App für UC2 Nachrichten-Triage mit animiertem Phil-Avatar, OpenAI TTS und Live-Exchange-Anbindung — deployed auf `kn-triage.butscher.cloud`.

**Architecture:** FastAPI-Backend serviert statisches Frontend (vanilla JS/HTML/CSS) über `StaticFiles`. Ein Docker-Container, Traefik-ready. Alle Credentials im Backend-RAM; kein Datenbank-Layer. Exchange-Logik aus `exchange_helpers.py` wird direkt wiederverwendet.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, anthropic, openai, exchangelib, python-dotenv, pytest, httpx · Vanilla JS (ES Modules, kein Build-Step), DM Sans (Google Fonts), CSS Custom Properties · Docker, docker-compose, Traefik

**Design Reference:** `docs/plans/2026-02-21-UC2-webapp-design.md` — PFLICHTLEKTÜRE vor der Implementierung.

**Arbeitsverzeichnis:** Alle Pfade relativ zu `UC2_Nachrichten_Triage/webapp/`

---

## Task 1: Projekt-Scaffold — Ordnerstruktur + Requirements

**Files:**
- Create: `webapp/backend/requirements.txt`
- Create: `webapp/backend/.env.example`
- Create: `webapp/backend/__init__.py` (leer)
- Create: `webapp/backend/exchange_helpers.py` (Kopie)
- Create: `webapp/tests/__init__.py` (leer)
- Create: `webapp/frontend/` (leeres Verzeichnis, Placeholder)

**Step 1: Ordnerstruktur anlegen**

```bash
cd "UC2_Nachrichten_Triage"
mkdir -p webapp/backend webapp/frontend webapp/tests
touch webapp/backend/__init__.py webapp/tests/__init__.py
```

**Step 2: `webapp/backend/requirements.txt` schreiben**

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
anthropic>=0.40.0
openai>=1.40.0
exchangelib>=5.1.0
python-dotenv>=1.0.0
httpx>=0.27.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

**Step 3: `webapp/backend/.env.example` schreiben**

```
ANTHROPIC_API_KEY=sk-ant-DEIN-KEY-HIER
OPENAI_API_KEY=sk-DEIN-OPENAI-KEY-HIER
```

**Step 4: `exchange_helpers.py` kopieren**

```bash
cp exchange_helpers.py webapp/backend/exchange_helpers.py
```

Verify: `wc -l webapp/backend/exchange_helpers.py` → sollte > 50 Zeilen zeigen.

**Step 5: Dependencies installieren**

```bash
pip install -r webapp/backend/requirements.txt
```

**Step 6: Commit**

```bash
git add webapp/
git commit -m "feat(webapp): scaffold — folder structure, requirements, exchange_helpers copy"
```

---

## Task 2: FastAPI-Skeleton + `/health` Endpoint (TDD)

**Files:**
- Create: `webapp/tests/test_api.py`
- Create: `webapp/backend/main.py`

**Kontext:** FastAPI wird mit `TestClient` von Starlette getestet (kein Mock nötig für Health). Der Client wird für alle weiteren API-Tests in dieser Datei wiederverwendet.

**Step 1: Failing Test schreiben — `webapp/tests/test_api.py`**

```python
# webapp/tests/test_api.py
import pytest
from fastapi.testclient import TestClient


def get_client():
    from backend.main import app
    return TestClient(app)


def test_health_returns_ok():
    client = get_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

**Step 2: Test ausführen und Fehler bestätigen**

```bash
cd webapp
pytest tests/test_api.py::test_health_returns_ok -v
```

Erwartet: `FAILED` mit `ModuleNotFoundError: No module named 'backend.main'`

**Step 3: `webapp/backend/main.py` schreiben**

```python
# webapp/backend/main.py
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI(title="UC2 Nachrichten-Triage", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


# Frontend statisch servieren (wird in späteren Tasks befüllt)
_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
```

**Step 4: Test ausführen und Erfolg bestätigen**

```bash
cd webapp
pytest tests/test_api.py::test_health_returns_ok -v
```

Erwartet: `PASSED`

**Step 5: Manuell prüfen**

```bash
cd webapp
uvicorn backend.main:app --reload --port 8001
# In zweitem Terminal:
curl http://localhost:8001/health
# Erwartet: {"status":"ok"}
```

Server stoppen (Ctrl+C).

**Step 6: Commit**

```bash
git add webapp/backend/main.py webapp/tests/test_api.py
git commit -m "feat(webapp): FastAPI skeleton + /health endpoint (TDD)"
```

---

## Task 3: `/api/analyze` Endpoint (TDD)

**Files:**
- Modify: `webapp/tests/test_api.py` — neue Tests anhängen
- Modify: `webapp/backend/main.py` — Endpoint + Analyzer-Logik hinzufügen

**Kontext:** Der Analyze-Endpoint übernimmt die CO-STAR-Logik aus dem Notebook. Der Claude-Client wird für Tests gemockt — kein echter API-Call in Tests.

**Step 1: Failing Tests schreiben — an `test_api.py` anhängen**

```python
# Ans Ende von webapp/tests/test_api.py anhängen:

import json


def test_analyze_returns_triage_json(mocker):
    """POST /api/analyze gibt ein gültiges Triage-Dict zurück."""
    mock_response = mocker.MagicMock()
    mock_response.content[0].text = json.dumps({
        "kategorie": "VIP",
        "priorität": 1,
        "zusammenfassung": "Dekan braucht Stellungnahme.",
        "empfohlene_aktion": "Sofort antworten.",
    })
    mocker.patch("backend.main.anthropic_client.messages.create",
                 return_value=mock_response)

    client = get_client()
    response = client.post("/api/analyze", json={"email_text": "Test-Mail"})
    assert response.status_code == 200
    data = response.json()
    assert data["kategorie"] == "VIP"
    assert data["priorität"] == 1
    assert "zusammenfassung" in data
    assert "empfohlene_aktion" in data


def test_analyze_rejects_empty_text(mocker):
    """Leerer email_text → 422."""
    client = get_client()
    response = client.post("/api/analyze", json={"email_text": ""})
    assert response.status_code == 422


def test_analyze_valid_kategorie(mocker):
    """Kategorie ist einer der vier erlaubten Werte."""
    VALID = {"VIP", "Aktion nötig", "Nur Info", "Ignorieren"}
    mock_response = mocker.MagicMock()
    mock_response.content[0].text = json.dumps({
        "kategorie": "Aktion nötig",
        "priorität": 2,
        "zusammenfassung": "Student fragt wegen Abgabe.",
        "empfohlene_aktion": "Bis Freitag antworten.",
    })
    mocker.patch("backend.main.anthropic_client.messages.create",
                 return_value=mock_response)

    client = get_client()
    response = client.post("/api/analyze", json={"email_text": "Test"})
    assert response.json()["kategorie"] in VALID
```

**Step 2: Tests ausführen und Fehler bestätigen**

```bash
cd webapp
pytest tests/test_api.py -k "analyze" -v
```

Erwartet: `FAILED` — Endpoint existiert noch nicht.

**Step 3: Analyzer-Logik + Endpoint in `main.py` ergänzen**

Direkt nach dem `health`-Endpoint, vor dem `StaticFiles`-Mount einfügen:

```python
import json
import re
import anthropic
from fastapi import HTTPException
from pydantic import BaseModel, field_validator

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

COSTAR_PROMPT = """\
C (Context): Du bist ein intelligenter E-Mail-Assistent für einen Hochschuldozenten.
Du hilfst dabei, eingehende E-Mails schnell zu priorisieren.

O (Objective): Analysiere die folgende E-Mail. Bestimme Kategorie, Priorität,
erstelle eine Kurzzusammenfassung und empfehle eine konkrete Aktion.

S (Style): Strukturiert, präzise, ohne Füllwörter.

T (Tone): Professionell und sachlich.

A (Audience): Der Dozent möchte in 5 Sekunden entscheiden,
welche Mails sofortige Aufmerksamkeit brauchen.

R (Response): Antworte AUSSCHLIESSLICH mit validem JSON — kein Text davor oder danach:
{{
    "kategorie": "VIP" | "Aktion nötig" | "Nur Info" | "Ignorieren",
    "priorität": 1 | 2 | 3 | 4,
    "zusammenfassung": "Max. 2 prägnante Sätze.",
    "empfohlene_aktion": "Konkrete, sofort umsetzbare Empfehlung."
}}

Kategorien:
- VIP (Priorität 1): Dekanat, Vorgesetzte, wichtige Partner
- Aktion nötig (Priorität 2): Studierende, Kollegen mit konkreten Anfragen
- Nur Info (Priorität 3): Newsletter, FYI-Mails ohne Handlungsbedarf
- Ignorieren (Priorität 4): Spam, Werbung, irrelevant

E-Mail:
{email_text}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


class AnalyzeRequest(BaseModel):
    email_text: str

    @field_validator("email_text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("email_text darf nicht leer sein")
        return v


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    prompt = COSTAR_PROMPT.format(email_text=req.email_text)
    response = anthropic_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = _strip_fences(response.content[0].text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Claude-Antwort kein gültiges JSON: {e}")
```

**Step 4: Tests ausführen und Erfolg bestätigen**

```bash
cd webapp
pytest tests/test_api.py -k "analyze" -v
```

Erwartet: alle 3 `analyze`-Tests `PASSED`.

**Step 5: Commit**

```bash
git add webapp/backend/main.py webapp/tests/test_api.py
git commit -m "feat(webapp): POST /api/analyze endpoint (TDD, CO-STAR)"
```

---

## Task 4: `/api/tts` Endpoint (TDD)

**Files:**
- Modify: `webapp/tests/test_api.py` — neue Tests
- Modify: `webapp/backend/main.py` — TTS-Endpoint

**Kontext:** OpenAI TTS gibt einen Audio-Stream zurück. Im Test mocken wir `openai_client.audio.speech.create` und prüfen Content-Type + Nicht-Leer-Antwort.

**Step 1: Failing Tests schreiben — an `test_api.py` anhängen**

```python
def test_tts_returns_audio(mocker):
    """POST /api/tts gibt audio/mpeg zurück."""
    mock_audio = mocker.MagicMock()
    mock_audio.content = b"FAKE_MP3_BYTES"
    mocker.patch("backend.main.openai_client.audio.speech.create",
                 return_value=mock_audio)

    client = get_client()
    response = client.post("/api/tts", json={"text": "Hallo Phil."})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert len(response.content) > 0


def test_tts_rejects_empty_text(mocker):
    """Leerer text → 422."""
    client = get_client()
    response = client.post("/api/tts", json={"text": ""})
    assert response.status_code == 422
```

**Step 2: Tests ausführen und Fehler bestätigen**

```bash
cd webapp
pytest tests/test_api.py -k "tts" -v
```

Erwartet: `FAILED`

**Step 3: TTS-Endpoint in `main.py` ergänzen**

Imports oben ergänzen:
```python
import openai
from fastapi.responses import StreamingResponse
import io
```

Nach dem analyze-Endpoint einfügen:

```python
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


class TTSRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text darf nicht leer sein")
        return v


@app.post("/api/tts")
def tts(req: TTSRequest):
    audio = openai_client.audio.speech.create(
        model="tts-1",
        voice="onyx",
        input=req.text,
        response_format="mp3",
    )
    return StreamingResponse(
        io.BytesIO(audio.content),
        media_type="audio/mpeg",
    )
```

**Step 4: Tests ausführen und Erfolg bestätigen**

```bash
cd webapp
pytest tests/test_api.py -k "tts" -v
```

Erwartet: beide TTS-Tests `PASSED`.

**Step 5: Commit**

```bash
git add webapp/backend/main.py webapp/tests/test_api.py
git commit -m "feat(webapp): POST /api/tts endpoint — OpenAI onyx, audio/mpeg (TDD)"
```

---

## Task 5: Exchange Endpoints — connect / fetch / disconnect (TDD)

**Files:**
- Modify: `webapp/tests/test_api.py` — neue Tests
- Modify: `webapp/backend/main.py` — 3 Endpoints + Session-Management

**Kontext:** Sessions werden in einem In-Memory-Dict gespeichert. Session-ID ist UUID4, wird als httpOnly-Cookie gesetzt. Der Exchange-Account aus `exchange_helpers.py` wird wiederverwendet.

**Step 1: Failing Tests schreiben**

```python
def test_exchange_connect_success(mocker):
    """POST /api/exchange/connect gibt inbox_count zurück und setzt Cookie."""
    mock_account = mocker.MagicMock()
    mock_account.inbox.total_count = 42
    mocker.patch("backend.main.connect_to_exchange", return_value=mock_account)

    client = get_client()
    response = client.post("/api/exchange/connect", json={
        "username": "robert.butscher",
        "password": "geheim",
        "institution": "THWS",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "connected"
    assert data["inbox_count"] == 42
    assert "session_id" in response.cookies


def test_exchange_connect_unknown_institution(mocker):
    """Unbekannte Institution → 400."""
    mocker.patch("backend.main.connect_to_exchange",
                 side_effect=ValueError("Unbekannte Institution"))
    client = get_client()
    response = client.post("/api/exchange/connect", json={
        "username": "x", "password": "y", "institution": "INVALID",
    })
    assert response.status_code == 400


def test_exchange_disconnect(mocker):
    """POST /api/exchange/disconnect löscht Session."""
    mock_account = mocker.MagicMock()
    mock_account.inbox.total_count = 1
    mocker.patch("backend.main.connect_to_exchange", return_value=mock_account)

    client = get_client()
    # Zuerst verbinden
    r = client.post("/api/exchange/connect", json={
        "username": "u", "password": "p", "institution": "THWS",
    })
    session_id = r.cookies["session_id"]

    # Trennen
    r2 = client.post("/api/exchange/disconnect",
                     cookies={"session_id": session_id})
    assert r2.status_code == 200
    assert r2.json()["status"] == "disconnected"


def test_exchange_fetch_requires_session(mocker):
    """POST /api/exchange/fetch ohne gültige Session → 401."""
    client = get_client()
    response = client.post("/api/exchange/fetch",
                           json={"max_count": 10, "unread_only": True},
                           cookies={"session_id": "ungueltig"})
    assert response.status_code == 401
```

**Step 2: Tests ausführen und Fehler bestätigen**

```bash
cd webapp
pytest tests/test_api.py -k "exchange" -v
```

Erwartet: alle 4 `FAILED`

**Step 3: Exchange-Endpoints in `main.py` ergänzen**

Imports oben:
```python
import uuid
from fastapi import Cookie
from backend.exchange_helpers import connect_to_exchange, fetch_emails
```

Nach TTS-Endpoint einfügen:

```python
# ── Session-Management (In-Memory) ────────────────────────────────────────────
_sessions: dict[str, object] = {}  # session_id → exchangelib Account


class ConnectRequest(BaseModel):
    username: str
    password: str
    institution: str


class FetchRequest(BaseModel):
    max_count: int = 10
    unread_only: bool = True


@app.post("/api/exchange/connect")
def exchange_connect(req: ConnectRequest, response_obj: "Response"):
    from fastapi import Response as FResponse
    try:
        account = connect_to_exchange(req.username, req.password, req.institution)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Exchange-Verbindung fehlgeschlagen: {e}")

    session_id = str(uuid.uuid4())
    _sessions[session_id] = account

    from fastapi import Response
    # Cookie wird via response gesetzt — Trick: wir nutzen JSONResponse direkt
    from fastapi.responses import JSONResponse
    resp = JSONResponse(content={
        "status": "connected",
        "inbox_count": account.inbox.total_count,
    })
    resp.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="strict",
        secure=False,  # True im Produktion (HTTPS via Traefik)
    )
    return resp


@app.post("/api/exchange/fetch")
def exchange_fetch(
    req: FetchRequest,
    session_id: str | None = Cookie(default=None),
):
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=401, detail="Keine gültige Session. Bitte zuerst verbinden.")
    account = _sessions[session_id]
    emails = fetch_emails(account, max_count=req.max_count, unread_only=req.unread_only)
    # _skipped-Sentinel entfernen
    skipped = 0
    if emails and "_skipped" in emails[-1]:
        skipped = emails[-1]["_skipped"]
        emails = emails[:-1]
    return {"emails": emails, "skipped": skipped}


@app.post("/api/exchange/disconnect")
def exchange_disconnect(session_id: str | None = Cookie(default=None)):
    if session_id and session_id in _sessions:
        del _sessions[session_id]
    from fastapi.responses import JSONResponse
    resp = JSONResponse(content={"status": "disconnected"})
    resp.delete_cookie("session_id")
    return resp
```

**Wichtig:** Den Import-Fix oben im File ergänzen — `Response` direkt aus fastapi:
```python
from fastapi import FastAPI, HTTPException, Cookie
from fastapi.responses import StreamingResponse, JSONResponse
```

**Step 4: Tests ausführen und Erfolg bestätigen**

```bash
cd webapp
pytest tests/test_api.py -v
```

Erwartet: Alle Tests `PASSED` (health + 3 analyze + 2 tts + 4 exchange = 10 Tests).

**Step 5: Commit**

```bash
git add webapp/backend/main.py webapp/tests/test_api.py
git commit -m "feat(webapp): Exchange endpoints connect/fetch/disconnect, in-memory sessions (TDD)"
```

---

## Task 6: Frontend HTML-Struktur + CSS Design-System

**Skill:** Verwende `frontend-design:frontend-design` für diesen Task — für Production-Grade-Ästhetik.

**Files:**
- Create: `webapp/frontend/index.html`
- Create: `webapp/frontend/style.css`

**Kontext:** Bauhaus-Design, DM Sans, viel Weißraum, nur 4px-Left-Border als Farbelement in Karten. Kein Framework, kein Build-Step. Alle Styles über CSS Custom Properties. Responsive: Desktop two-column, Mobile single-column.

**Step 1: `webapp/frontend/index.html` schreiben**

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>PHIL · Nachrichten-Triage</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap" rel="stylesheet"/>
  <link rel="stylesheet" href="style.css"/>
</head>
<body>

  <!-- ── Header ──────────────────────────────────────────────────────────── -->
  <header class="site-header">
    <span class="site-header__brand">PHIL</span>
    <span class="site-header__title">Nachrichten-Triage</span>
    <span class="site-header__year">1987 → 2026</span>
  </header>

  <!-- ── Main Layout ─────────────────────────────────────────────────────── -->
  <main class="layout">

    <!-- Phil-Spalte -->
    <aside class="phil-column">

      <!-- Avatar -->
      <div class="phil-avatar" data-state="idle" id="phil">
        <svg viewBox="0 0 120 144" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <!-- Hals -->
          <rect x="48" y="116" width="24" height="20" rx="6" fill="#18181B"/>
          <!-- Kopf -->
          <ellipse cx="60" cy="66" rx="50" ry="56" fill="#18181B"/>
          <!-- Augenhöhlen -->
          <circle cx="42" cy="57" r="11" fill="white"/>
          <circle cx="78" cy="57" r="11" fill="white"/>
          <!-- Iris -->
          <ellipse class="iris iris--left"  cx="43" cy="58" rx="5.5" ry="5.5" fill="#18181B"/>
          <ellipse class="iris iris--right" cx="79" cy="58" rx="5.5" ry="5.5" fill="#18181B"/>
          <!-- Glanzpunkt -->
          <circle cx="45" cy="56" r="2"  fill="white"/>
          <circle cx="81" cy="56" r="2"  fill="white"/>
          <!-- Mund -->
          <rect class="mouth" x="42" y="80" width="36" height="6" rx="3" fill="white"/>
        </svg>
      </div>

      <!-- Sprechblase -->
      <div class="speech-bubble" id="speech-bubble" aria-live="polite">
        <p class="speech-bubble__text" id="speech-text"></p>
      </div>

      <!-- Audio-Controls -->
      <div class="audio-controls" id="audio-controls" hidden>
        <canvas class="waveform" id="waveform" width="120" height="32" aria-hidden="true"></canvas>
        <div class="audio-buttons">
          <button class="audio-btn" id="btn-play"  aria-label="Abspielen">▶</button>
          <button class="audio-btn" id="btn-pause" aria-label="Pause">⏸</button>
          <button class="audio-btn" id="btn-stop"  aria-label="Stopp">⏹</button>
        </div>
      </div>

    </aside>

    <!-- Rechte Spalte: Input + Ergebnisse -->
    <section class="content-column">

      <!-- Tabs -->
      <div class="tabs" role="tablist">
        <button class="tab tab--active" role="tab" aria-selected="true"
                data-tab="paste" id="tab-paste">
          E-Mail einfügen
        </button>
        <button class="tab" role="tab" aria-selected="false"
                data-tab="exchange" id="tab-exchange">
          Live Exchange
        </button>
      </div>

      <!-- Panel: Paste-Modus -->
      <div class="tab-panel" id="panel-paste" role="tabpanel">
        <label class="field-label" for="email-input">E-Mail-Text</label>
        <textarea
          id="email-input"
          class="email-textarea"
          placeholder="Von: name@example.com&#10;Betreff: Betreffzeile&#10;&#10;Text der E-Mail..."
          rows="9"
          aria-label="E-Mail-Text einfügen"
        ></textarea>
        <button class="btn btn--primary" id="btn-analyze">
          Analysieren
        </button>
      </div>

      <!-- Panel: Exchange-Modus -->
      <div class="tab-panel tab-panel--hidden" id="panel-exchange" role="tabpanel">

        <!-- Credential-Form (sichtbar wenn nicht verbunden) -->
        <form class="credential-form" id="credential-form" novalidate>
          <div class="form-row">
            <label class="field-label" for="institution">Institution</label>
            <select class="select" id="institution" name="institution">
              <option value="THWS">THWS Würzburg-Schweinfurt</option>
              <option value="DHBW">DHBW</option>
            </select>
          </div>
          <div class="form-row">
            <label class="field-label" for="username">Benutzername</label>
            <input class="input" id="username" name="username" type="text"
                   placeholder="vorname.nachname" autocomplete="off" spellcheck="false"/>
          </div>
          <div class="form-row">
            <label class="field-label" for="password">Passwort</label>
            <input class="input" id="password" name="password" type="password"
                   placeholder="••••••••" autocomplete="off"/>
          </div>
          <p class="security-notice">
            ⚠ Ihre Daten werden nicht gespeichert — nur im Arbeitsspeicher dieser Session.
          </p>
          <div class="form-actions">
            <button type="submit" class="btn btn--primary" id="btn-connect">
              Verbinden
            </button>
          </div>
        </form>

        <!-- Connected-State (versteckt wenn nicht verbunden) -->
        <div class="connected-state" id="connected-state" hidden>
          <div class="connected-info" id="connected-info"></div>
          <div class="live-controls">
            <label class="field-label">
              <input type="checkbox" id="unread-only" checked/>
              Nur ungelesene E-Mails
            </label>
            <label class="field-label">
              Max. Mails:
              <input type="number" id="max-count" value="10" min="1" max="50"
                     class="input input--narrow"/>
            </label>
          </div>
          <div class="form-actions">
            <button class="btn btn--primary" id="btn-live-triage">
              Live-Triage starten
            </button>
            <button class="btn btn--ghost" id="btn-disconnect">
              Trennen
            </button>
          </div>
        </div>

      </div>

      <!-- Ergebnis-Bereich -->
      <div class="results" id="results" aria-live="polite"></div>

    </section>
  </main>

  <!-- ── Hidden Audio Player ─────────────────────────────────────────────── -->
  <audio id="audio-player" aria-hidden="true"></audio>

  <script type="module" src="app.js"></script>
</body>
</html>
```

**Step 2: `webapp/frontend/style.css` schreiben**

```css
/* ── Reset & Base ─────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── Design Tokens ───────────────────────────────────────────────────────── */
:root {
  --bg:           #FAFAF8;
  --surface:      #FFFFFF;
  --surface-2:    #F4F4F1;
  --border:       #E8E8E4;
  --text-primary: #18181B;
  --text-secondary: #71717A;
  --text-muted:   #A1A1AA;
  --accent:       #E85D04;
  --accent-light: #FFF4EE;

  --vip:          #DC2626;
  --aktion:       #D97706;
  --info:         #2563EB;
  --ignorieren:   #9CA3AF;

  --font: 'DM Sans', 'Inter', system-ui, sans-serif;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;

  --space-1: 8px;
  --space-2: 16px;
  --space-3: 24px;
  --space-4: 32px;
  --space-6: 48px;
  --space-8: 64px;

  --shadow-sm: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.08);

  --transition: 200ms ease;
}

/* ── Typography ──────────────────────────────────────────────────────────── */
html {
  font-family: var(--font);
  font-size: 16px;
  color: var(--text-primary);
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ── Header ──────────────────────────────────────────────────────────────── */
.site-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.site-header__brand {
  font-size: 1.125rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--text-primary);
}

.site-header__title {
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.site-header__year {
  margin-left: auto;
  font-size: 0.8125rem;
  font-weight: 400;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

/* ── Layout ──────────────────────────────────────────────────────────────── */
.layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  max-width: 1080px;
  margin: 0 auto;
  min-height: calc(100vh - 65px);
  gap: 0;
}

/* ── Phil-Spalte ─────────────────────────────────────────────────────────── */
.phil-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-6) var(--space-4);
  border-right: 1px solid var(--border);
  position: sticky;
  top: 0;
  height: calc(100vh - 65px);
  overflow: hidden;
}

/* Phil Avatar */
.phil-avatar {
  width: 120px;
  height: 140px;
  flex-shrink: 0;
}

.phil-avatar svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

/* Iris-Blinzeln */
@keyframes blink {
  0%, 88%, 100% { transform: scaleY(1); }
  92%           { transform: scaleY(0.06); }
}
.iris {
  transform-origin: center;
  animation: blink 4.5s ease-in-out infinite;
}
.iris--right { animation-delay: 0.08s; }

/* Sprechen: Mund-Animation */
@keyframes speak {
  from { height: 6px; transform: translateY(0);    }
  to   { height: 13px; transform: translateY(-3px); }
}
[data-state="speaking"] .mouth {
  animation: speak 0.13s ease-in-out infinite alternate;
}

/* Denken: Augen leicht nach oben-links */
[data-state="thinking"] .iris--left  { transform: translate(-2px, -2px); }
[data-state="thinking"] .iris--right { transform: translate(-2px, -2px); }

/* Nicken wenn fertig */
@keyframes nod {
  0%   { transform: translateY(0); }
  40%  { transform: translateY(4px); }
  100% { transform: translateY(0); }
}
[data-state="done"] svg { animation: nod 0.35s ease-in-out; }

/* Sprechblase */
.speech-bubble {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-2);
  width: 100%;
  min-height: 72px;
  box-shadow: var(--shadow-sm);
}
.speech-bubble::before {
  content: '';
  position: absolute;
  top: -8px;
  left: 50%;
  transform: translateX(-50%);
  border: 8px solid transparent;
  border-bottom-color: var(--border);
  border-top: none;
  filter: drop-shadow(0 -1px 0 var(--border));
}
.speech-bubble::after {
  content: '';
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  border: 7px solid transparent;
  border-bottom-color: var(--surface);
  border-top: none;
}

.speech-bubble__text {
  font-size: 0.875rem;
  line-height: 1.55;
  color: var(--text-primary);
  min-height: 2.6em;
}

/* Audio-Controls */
.audio-controls {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  width: 100%;
}

.waveform {
  width: 120px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.audio-buttons {
  display: flex;
  gap: var(--space-1);
}

.audio-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  width: 36px;
  height: 36px;
  font-size: 0.875rem;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--transition);
}
.audio-btn:hover {
  background: var(--surface-2);
  color: var(--text-primary);
}

/* ── Content-Spalte ──────────────────────────────────────────────────────── */
.content-column {
  padding: var(--space-6) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
.tabs {
  display: flex;
  gap: 2px;
  background: var(--surface-2);
  border-radius: var(--radius-md);
  padding: 3px;
  width: fit-content;
}

.tab {
  padding: var(--space-1) var(--space-3);
  border: none;
  background: transparent;
  border-radius: calc(var(--radius-md) - 2px);
  font-family: var(--font);
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
}
.tab:hover { color: var(--text-primary); }
.tab--active {
  background: var(--surface);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

/* ── Tab Panels ──────────────────────────────────────────────────────────── */
.tab-panel { display: flex; flex-direction: column; gap: var(--space-2); }
.tab-panel--hidden { display: none; }

/* ── Form Elements ───────────────────────────────────────────────────────── */
.field-label {
  display: block;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.email-textarea {
  width: 100%;
  padding: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-family: var(--font);
  font-size: 0.9375rem;
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--surface);
  resize: vertical;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.email-textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 15%, transparent);
}
.email-textarea::placeholder { color: var(--text-muted); }

.input {
  width: 100%;
  padding: 10px var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: var(--font);
  font-size: 0.9375rem;
  color: var(--text-primary);
  background: var(--surface);
  transition: border-color var(--transition), box-shadow var(--transition);
}
.input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 15%, transparent);
}
.input--narrow { width: 80px; }

.select {
  width: 100%;
  padding: 10px var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: var(--font);
  font-size: 0.9375rem;
  color: var(--text-primary);
  background: var(--surface);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2371717A' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 36px;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 11px var(--space-3);
  border-radius: var(--radius-sm);
  font-family: var(--font);
  font-size: 0.9375rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition);
  border: 1px solid transparent;
  white-space: nowrap;
}
.btn--primary {
  background: var(--text-primary);
  color: white;
  border-color: var(--text-primary);
}
.btn--primary:hover {
  background: #2d2d30;
}
.btn--primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn--ghost {
  background: transparent;
  color: var(--text-secondary);
  border-color: var(--border);
}
.btn--ghost:hover {
  background: var(--surface-2);
  color: var(--text-primary);
}

/* ── Credential Form ─────────────────────────────────────────────────────── */
.credential-form { display: flex; flex-direction: column; gap: var(--space-2); max-width: 380px; }
.form-row { display: flex; flex-direction: column; }
.form-actions { display: flex; gap: var(--space-2); align-items: center; margin-top: var(--space-1); }
.security-notice {
  font-size: 0.8125rem;
  color: var(--text-muted);
  line-height: 1.5;
}

.connected-state { display: flex; flex-direction: column; gap: var(--space-3); }
.connected-info {
  font-size: 0.9375rem;
  color: var(--text-primary);
  padding: var(--space-2) var(--space-2);
  background: var(--surface-2);
  border-radius: var(--radius-sm);
}
.live-controls { display: flex; flex-direction: column; gap: var(--space-1); }

/* ── Ergebnis-Karten ─────────────────────────────────────────────────────── */
.results { display: flex; flex-direction: column; gap: var(--space-2); }

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  border-left-width: 4px;
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: box-shadow var(--transition);
  opacity: 0;
  transform: translateY(8px);
  animation: card-in 300ms ease forwards;
}
.card:hover { box-shadow: var(--shadow-md); }

@keyframes card-in {
  to { opacity: 1; transform: translateY(0); }
}

.card--vip        { border-left-color: var(--vip); }
.card--aktion     { border-left-color: var(--aktion); }
.card--info       { border-left-color: var(--info); }
.card--ignorieren { border-left-color: var(--ignorieren); }

.card__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  user-select: none;
}

.card__prio {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}
.card--vip        .card__prio { color: var(--vip); }
.card--aktion     .card__prio { color: var(--aktion); }
.card--info       .card__prio { color: var(--info); }
.card--ignorieren .card__prio { color: var(--ignorieren); }

.card__summary {
  flex: 1;
  font-size: 0.9375rem;
  color: var(--text-primary);
  line-height: 1.5;
}

.card__play-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 50%;
  width: 32px;
  height: 32px;
  font-size: 0.8rem;
  cursor: pointer;
  color: var(--text-secondary);
  flex-shrink: 0;
  transition: all var(--transition);
  display: flex;
  align-items: center;
  justify-content: center;
}
.card__play-btn:hover {
  background: var(--surface-2);
  color: var(--text-primary);
}

.card__details {
  max-height: 0;
  overflow: hidden;
  transition: max-height 320ms ease;
}
.card__details--open { max-height: 200px; }

.card__details-inner {
  padding: 0 var(--space-3) var(--space-2);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.card__detail-label {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-top: var(--space-1);
}
.card__detail-value {
  font-size: 0.9375rem;
  color: var(--text-primary);
  line-height: 1.5;
}
.card__meta {
  font-size: 0.8125rem;
  color: var(--text-muted);
  margin-top: var(--space-1);
}

/* ── Loading Spinner ─────────────────────────────────────────────────────── */
.spinner {
  display: inline-block;
  width: 18px; height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--text-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .layout {
    grid-template-columns: 1fr;
  }
  .phil-column {
    position: static;
    height: auto;
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: center;
    padding: var(--space-4) var(--space-3);
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .phil-avatar { width: 80px; height: 93px; }
  .speech-bubble { flex: 1; min-width: 180px; }
  .content-column { padding: var(--space-4) var(--space-3); }
}
```

**Step 3: Manuell im Browser prüfen**

```bash
cd webapp
uvicorn backend.main:app --reload --port 8001
```

Browser öffnen: `http://localhost:8001`
- Phil (schwarzer geometrischer Kopf) sichtbar ✓
- Augen blinzeln alle ~4.5s ✓
- Tabs "E-Mail einfügen" / "Live Exchange" ✓
- Textarea vorhanden ✓
- Layout two-column auf Desktop ✓

**Step 4: Commit**

```bash
git add webapp/frontend/
git commit -m "feat(webapp): HTML structure + Bauhaus CSS design system, Phil SVG avatar"
```

---

## Task 7: app.js — Paste-Modus (Analyse + Karten)

**Files:**
- Create: `webapp/frontend/app.js`

**Kontext:** Vanilla JS, ES Module. Kein Framework. Strikte Trennung: `state`, `api`, `ui` als interne Module. Der Paste-Modus ruft `POST /api/analyze` auf und rendert Ergebnis-Karten mit staggered animation.

**Step 1: `webapp/frontend/app.js` schreiben**

```javascript
// webapp/frontend/app.js
'use strict';

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  exchangeConnected: false,
  currentAudio: null,
};

// ── DOM Refs ──────────────────────────────────────────────────────────────
const phil          = document.getElementById('phil');
const speechText    = document.getElementById('speech-text');
const speechBubble  = document.getElementById('speech-bubble');
const audioControls = document.getElementById('audio-controls');
const audioPlayer   = document.getElementById('audio-player');
const waveformCanvas = document.getElementById('waveform');

const tabs          = document.querySelectorAll('.tab');
const panels        = document.querySelectorAll('.tab-panel');

const emailInput    = document.getElementById('email-input');
const btnAnalyze    = document.getElementById('btn-analyze');
const resultsEl     = document.getElementById('results');

// Exchange
const credentialForm   = document.getElementById('credential-form');
const connectedState   = document.getElementById('connected-state');
const connectedInfo    = document.getElementById('connected-info');
const btnConnect       = document.getElementById('btn-connect');
const btnDisconnect    = document.getElementById('btn-disconnect');
const btnLiveTriage    = document.getElementById('btn-live-triage');

// Audio buttons
const btnPlay  = document.getElementById('btn-play');
const btnPause = document.getElementById('btn-pause');
const btnStop  = document.getElementById('btn-stop');

// ── Helpers ───────────────────────────────────────────────────────────────
function setPhilState(s) {
  phil.dataset.state = s;
}

let _typewriterTimer = null;
function typewrite(text, delay = 20) {
  speechText.textContent = '';
  clearTimeout(_typewriterTimer);
  let i = 0;
  function step() {
    if (i < text.length) {
      speechText.textContent += text[i++];
      _typewriterTimer = setTimeout(step, delay);
    }
  }
  step();
}

function philSay(text) {
  typewrite(text);
}

// ── Kategorie → CSS-Klasse + Emoji ───────────────────────────────────────
const KATEGORIE_META = {
  'VIP':          { cls: 'card--vip',        emoji: '🔴', label: 'VIP' },
  'Aktion nötig': { cls: 'card--aktion',     emoji: '🟡', label: 'Aktion nötig' },
  'Nur Info':     { cls: 'card--info',       emoji: '🔵', label: 'Nur Info' },
  'Ignorieren':   { cls: 'card--ignorieren', emoji: '⚫', label: 'Ignorieren' },
};

// ── Karte rendern ─────────────────────────────────────────────────────────
function renderCard(result, index, emailPreview = '') {
  const meta = KATEGORIE_META[result.kategorie] ?? KATEGORIE_META['Ignorieren'];
  const card = document.createElement('div');
  card.className = `card ${meta.cls}`;
  card.style.animationDelay = `${index * 80}ms`;

  // Sprechtext für TTS
  const ttsText =
    `${meta.label}. Priorität ${result.priorität}. ` +
    `${result.zusammenfassung} ` +
    `Empfehlung: ${result.empfohlene_aktion}`;

  card.innerHTML = `
    <div class="card__header" role="button" tabindex="0"
         aria-expanded="false" aria-controls="card-detail-${index}">
      <span class="card__prio">${meta.emoji} ${meta.label} · ${result.priorität}/4</span>
      <span class="card__summary">${escHtml(result.zusammenfassung)}</span>
      <button class="card__play-btn" aria-label="Vorlesen" data-tts="${escAttr(ttsText)}">▶</button>
    </div>
    <div class="card__details" id="card-detail-${index}" role="region">
      <div class="card__details-inner">
        <span class="card__detail-label">Empfehlung</span>
        <span class="card__detail-value">${escHtml(result.empfohlene_aktion)}</span>
        ${emailPreview ? `<span class="card__meta">Vorschau: ${escHtml(emailPreview.slice(0, 100))}…</span>` : ''}
      </div>
    </div>
  `;

  // Expand/Collapse
  const header  = card.querySelector('.card__header');
  const details = card.querySelector('.card__details');
  header.addEventListener('click', (e) => {
    if (e.target.closest('.card__play-btn')) return;
    const open = details.classList.toggle('card__details--open');
    header.setAttribute('aria-expanded', open);
  });
  header.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      header.click();
    }
  });

  // Play-Button
  card.querySelector('.card__play-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    const text = e.currentTarget.dataset.tts;
    playTTS(text);
  });

  return card;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escAttr(s) { return escHtml(s); }

// ── API ───────────────────────────────────────────────────────────────────
async function apiAnalyze(emailText) {
  const res = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email_text: emailText }),
  });
  if (!res.ok) throw new Error(`Analyse fehlgeschlagen (${res.status})`);
  return res.json();
}

async function apiTTS(text) {
  const res = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`TTS fehlgeschlagen (${res.status})`);
  return res.blob();
}

// ── TTS Playback ──────────────────────────────────────────────────────────
async function playTTS(text) {
  try {
    setPhilState('thinking');
    const blob = await apiTTS(text);
    const url  = URL.createObjectURL(blob);

    if (state.currentAudio) {
      URL.revokeObjectURL(state.currentAudio);
    }
    state.currentAudio = url;

    audioPlayer.src = url;
    audioPlayer.play();
    audioControls.hidden = false;
    drawWaveformIdle();
  } catch (err) {
    setPhilState('idle');
    console.error('TTS error:', err);
  }
}

audioPlayer.addEventListener('play',  () => { setPhilState('speaking'); drawWaveformAnimated(); });
audioPlayer.addEventListener('pause', () => { setPhilState('idle');     stopWaveform(); });
audioPlayer.addEventListener('ended', () => {
  setPhilState('done');
  setTimeout(() => setPhilState('idle'), 400);
  stopWaveform();
});

btnPlay.addEventListener('click',  () => audioPlayer.play());
btnPause.addEventListener('click', () => audioPlayer.pause());
btnStop.addEventListener('click',  () => { audioPlayer.pause(); audioPlayer.currentTime = 0; });

// ── Waveform (Canvas, simpel) ─────────────────────────────────────────────
let _waveAnim = null;
const waveCtx = waveformCanvas.getContext('2d');

function drawWaveformIdle() {
  waveCtx.clearRect(0, 0, 120, 32);
  waveCtx.fillStyle = getComputedStyle(document.documentElement)
    .getPropertyValue('--text-muted').trim();
  for (let x = 4; x < 116; x += 6) {
    waveCtx.fillRect(x, 14, 3, 4);
  }
}

function drawWaveformAnimated() {
  stopWaveform();
  function frame() {
    waveCtx.clearRect(0, 0, 120, 32);
    waveCtx.fillStyle = '#18181B';
    const t = Date.now() / 200;
    for (let i = 0; i < 18; i++) {
      const x = 4 + i * 6.5;
      const h = 4 + Math.abs(Math.sin(t + i * 0.8)) * 18;
      waveCtx.fillRect(x, 16 - h / 2, 3, h);
    }
    _waveAnim = requestAnimationFrame(frame);
  }
  frame();
}

function stopWaveform() {
  if (_waveAnim) { cancelAnimationFrame(_waveAnim); _waveAnim = null; }
  drawWaveformIdle();
}

// ── Tab-Switching ─────────────────────────────────────────────────────────
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => { t.classList.remove('tab--active'); t.setAttribute('aria-selected', 'false'); });
    panels.forEach(p => p.classList.add('tab-panel--hidden'));

    tab.classList.add('tab--active');
    tab.setAttribute('aria-selected', 'true');
    const targetId = `panel-${tab.dataset.tab}`;
    document.getElementById(targetId).classList.remove('tab-panel--hidden');
  });
});

// ── Paste-Modus: Analyse ──────────────────────────────────────────────────
btnAnalyze.addEventListener('click', async () => {
  const text = emailInput.value.trim();
  if (!text) {
    philSay('Bitte zuerst einen E-Mail-Text einfügen.');
    return;
  }

  btnAnalyze.disabled = true;
  btnAnalyze.innerHTML = '<span class="spinner"></span> Analysiere…';
  setPhilState('thinking');
  philSay('Ich analysiere die E-Mail…');
  resultsEl.innerHTML = '';

  try {
    const result = await apiAnalyze(text);
    resultsEl.appendChild(renderCard(result, 0, text));

    const summary =
      `Analyse abgeschlossen. Kategorie: ${result.kategorie}. ` +
      `${result.zusammenfassung}`;
    philSay(summary);
    await playTTS(summary);
  } catch (err) {
    philSay(`Fehler: ${err.message}`);
    setPhilState('idle');
  } finally {
    btnAnalyze.disabled = false;
    btnAnalyze.innerHTML = 'Analysieren';
  }
});
```

**Step 2: Manuell testen**

```bash
# Server läuft auf Port 8001 (aus Task 6)
# Browser: http://localhost:8001
# 1. E-Mail-Text einfügen (z.B. Inhalt von sample_emails/email_01_vip.txt)
# 2. "Analysieren" klicken
# 3. Prüfen: Phil wechselt zu "thinking", dann Karte erscheint, Phil spricht
# 4. Karte expandieren bei Klick
# 5. ▶-Button: Phil liest Karte vor
```

**Step 3: Commit**

```bash
git add webapp/frontend/app.js
git commit -m "feat(webapp): app.js — paste mode, card rendering, TTS playback, Phil animation"
```

---

## Task 8: app.js — Exchange-Modus ergänzen

**Files:**
- Modify: `webapp/frontend/app.js` — Exchange-Logik anhängen

**Step 1: Exchange-Logik ans Ende von `app.js` anhängen**

```javascript
// ── Exchange API ──────────────────────────────────────────────────────────
async function apiConnect(username, password, institution) {
  const res = await fetch('/api/exchange/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, institution }),
    credentials: 'same-origin',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Verbindung fehlgeschlagen' }));
    throw new Error(err.detail ?? 'Verbindung fehlgeschlagen');
  }
  return res.json();
}

async function apiDisconnect() {
  await fetch('/api/exchange/disconnect', {
    method: 'POST',
    credentials: 'same-origin',
  });
}

async function apiFetch(maxCount, unreadOnly) {
  const res = await fetch('/api/exchange/fetch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ max_count: maxCount, unread_only: unreadOnly }),
    credentials: 'same-origin',
  });
  if (!res.ok) throw new Error('Fetch fehlgeschlagen — bitte erneut verbinden.');
  return res.json();
}

// ── Institution Placeholder ───────────────────────────────────────────────
const usernameInput   = document.getElementById('username');
const institutionSel  = document.getElementById('institution');
const INSTITUTION_HINTS = {
  THWS: 'vorname.nachname',
  DHBW: 'vollstaendige@email.de',
};
institutionSel.addEventListener('change', () => {
  usernameInput.placeholder = INSTITUTION_HINTS[institutionSel.value] ?? '';
  usernameInput.value = '';
});

// ── Connect ───────────────────────────────────────────────────────────────
credentialForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const username    = usernameInput.value.trim();
  const password    = document.getElementById('password').value;
  const institution = institutionSel.value;

  if (!username || !password) {
    philSay('Bitte Benutzername und Passwort eingeben.');
    return;
  }

  btnConnect.disabled = true;
  btnConnect.innerHTML = '<span class="spinner"></span> Verbinde…';
  setPhilState('thinking');
  philSay('Verbinde mit Exchange…');

  try {
    const data = await apiConnect(username, password, institution);
    state.exchangeConnected = true;

    // Passwort sofort löschen
    document.getElementById('password').value = '';

    credentialForm.hidden  = true;
    connectedState.hidden  = false;
    connectedInfo.textContent =
      `✓ Verbunden mit ${institution} · ${data.inbox_count} Mails im Posteingang`;

    const msg = `Verbindung hergestellt. Sie haben ${data.inbox_count} Mails.`;
    philSay(msg);
    await playTTS(msg);
  } catch (err) {
    philSay(`Verbindung fehlgeschlagen: ${err.message}`);
    setPhilState('idle');
  } finally {
    btnConnect.disabled = false;
    btnConnect.innerHTML = 'Verbinden';
  }
});

// ── Disconnect ────────────────────────────────────────────────────────────
btnDisconnect.addEventListener('click', async () => {
  await apiDisconnect();
  state.exchangeConnected = false;
  credentialForm.hidden = false;
  connectedState.hidden = true;
  resultsEl.innerHTML   = '';
  philSay('Verbindung getrennt.');
});

// ── Live-Triage ───────────────────────────────────────────────────────────
btnLiveTriage.addEventListener('click', async () => {
  const maxCount  = parseInt(document.getElementById('max-count').value, 10) || 10;
  const unreadOnly = document.getElementById('unread-only').checked;

  btnLiveTriage.disabled = true;
  btnLiveTriage.innerHTML = '<span class="spinner"></span> Lade Mails…';
  setPhilState('thinking');
  philSay('Lade E-Mails aus dem Postfach…');
  resultsEl.innerHTML = '';

  try {
    const { emails, skipped } = await apiFetch(maxCount, unreadOnly);

    if (emails.length === 0) {
      philSay('Keine E-Mails gefunden.');
      setPhilState('idle');
      return;
    }

    philSay(`Analysiere ${emails.length} E-Mail${emails.length !== 1 ? 's' : ''}…`);

    const results = [];
    for (const email of emails) {
      const emailText =
        `Von: ${email.sender}\nBetreff: ${email.subject}\n\n${email.body ?? ''}`;
      const result = await apiAnalyze(emailText);
      results.push({ result, email });
    }

    results.forEach(({ result, email }, i) => {
      resultsEl.appendChild(renderCard(result, i, email.subject));
    });

    const vipCount    = results.filter(r => r.result.kategorie === 'VIP').length;
    const aktionCount = results.filter(r => r.result.kategorie === 'Aktion nötig').length;
    const parts = [];
    if (vipCount)    parts.push(`${vipCount} VIP-Mail${vipCount !== 1 ? 's' : ''}`);
    if (aktionCount) parts.push(`${aktionCount} Aktion nötig`);
    const summary = parts.length
      ? `Analyse abgeschlossen. ${parts.join(', ')} — sofortige Aufmerksamkeit erforderlich.`
      : `Analyse abgeschlossen. Keine dringenden Mails.`;

    if (skipped > 0) {
      const notice = document.createElement('p');
      notice.style.cssText = 'font-size:.8125rem;color:var(--text-muted);margin-top:8px';
      notice.textContent = `⚠ ${skipped} Mail${skipped !== 1 ? 's' : ''} konnten nicht geladen werden.`;
      resultsEl.appendChild(notice);
    }

    philSay(summary);
    await playTTS(summary);
  } catch (err) {
    philSay(`Fehler: ${err.message}`);
    setPhilState('idle');
  } finally {
    btnLiveTriage.disabled = false;
    btnLiveTriage.innerHTML = 'Live-Triage starten';
  }
});
```

**Step 2: Manuell testen (Exchange optional — Paste-Modus reicht)**

```bash
# Browser: http://localhost:8001
# Tab "Live Exchange" klicken
# Credential-Form sichtbar ✓
# Institution wählen → Placeholder wechselt ✓
# Mit echten THWS-Zugangsdaten testen falls verfügbar
# Disconnect: Form erscheint wieder ✓
```

**Step 3: Commit**

```bash
git add webapp/frontend/app.js
git commit -m "feat(webapp): app.js — Exchange mode, live triage, connect/disconnect"
```

---

## Task 9: Dockerfile + docker-compose.yml

**Files:**
- Create: `webapp/Dockerfile`
- Create: `webapp/docker-compose.yml`
- Create: `webapp/backend/.env` (lokal, nicht committed)

**Step 1: `webapp/Dockerfile` schreiben**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Source
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Port
EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: `webapp/docker-compose.yml` schreiben**

```yaml
services:
  triage:
    build: .
    env_file: backend/.env
    ports:
      - "8000:8000"          # lokal testen; im Prod via Traefik
    restart: unless-stopped
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.triage.rule=Host(`kn-triage.butscher.cloud`)"
      - "traefik.http.routers.triage.entrypoints=websecure"
      - "traefik.http.routers.triage.tls.certresolver=letsencrypt"
      - "traefik.http.services.triage.loadbalancer.server.port=8000"

networks:
  default:
    name: traefik-net
    external: true
```

**Step 3: `.env` für lokalen Test anlegen (nicht committen)**

```bash
cp webapp/backend/.env.example webapp/backend/.env
# .env öffnen und echte Keys eintragen
```

**Step 4: Docker-Build testen**

```bash
cd webapp
docker build -t uc2-triage .
```

Erwartet: `Successfully built ...`

**Step 5: Container starten und prüfen**

```bash
docker run --rm -p 8002:8000 --env-file backend/.env uc2-triage
# In zweitem Terminal:
curl http://localhost:8002/health
# Erwartet: {"status":"ok"}
# Browser: http://localhost:8002 → UI lädt
```

Container stoppen (Ctrl+C).

**Step 6: `.dockerignore` anlegen**

```
webapp/backend/.env
webapp/backend/__pycache__/
webapp/tests/
**/__pycache__/
*.pyc
.git
```

**Step 7: Commit**

```bash
git add webapp/Dockerfile webapp/docker-compose.yml webapp/.dockerignore
git commit -m "feat(webapp): Dockerfile + docker-compose.yml, Traefik-ready"
```

---

## Task 10: Alle Tests grün + README ergänzen

**Files:**
- Modify: `webapp/backend/main.py` — finale Prüfung
- Modify: `UC2_Nachrichten_Triage/README.md` — Webapp-Abschnitt

**Step 1: Alle Tests ausführen**

```bash
cd webapp
pytest tests/ -v
```

Erwartet: alle Tests `PASSED`. Wenn Tests fehlschlagen: Fehler beheben, dann weiter.

**Step 2: README.md — Webapp-Abschnitt anhängen**

An das Ende von `UC2_Nachrichten_Triage/README.md` anhängen:

```markdown
## Stufe 3: Web-App (kn-triage.butscher.cloud)

### Lokaler Start

```bash
cd webapp
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # Keys eintragen
uvicorn backend.main:app --reload --port 8001
# Browser: http://localhost:8001
```

### Docker

```bash
cd webapp
cp backend/.env.example backend/.env   # Keys eintragen
docker compose up --build
# Browser: http://localhost:8000
```

### Deployment (butscher.cloud VPS)

```bash
# Auf dem Server:
git pull
cd UC2_Nachrichten_Triage/webapp
docker compose up -d --build
```

Traefik routet automatisch `kn-triage.butscher.cloud` → Container Port 8000.

### Features

| Feature | Beschreibung |
|---------|-------------|
| Phil-Avatar | Animierter CSS/SVG Assistent |
| TTS | OpenAI `tts-1`, Stimme `onyx` (Deutsch) |
| Paste-Modus | E-Mail einfügen → sofortige Analyse |
| Live Exchange | THWS/DHBW Exchange-Anbindung via EWS |
| Bauhaus-Design | DM Sans, Warmweiß, viel Weißraum |
```

**Step 3: Finaler Commit**

```bash
git add UC2_Nachrichten_Triage/README.md webapp/
git commit -m "feat(webapp): all tests green, README updated — UC2 web-app complete"
```

---

## Implementierungs-Checkliste

| Task | Inhalt | Tests |
|------|--------|-------|
| 1 | Scaffold, requirements, exchange_helpers copy | manuell |
| 2 | FastAPI skeleton + /health | pytest: 1 Test |
| 3 | POST /api/analyze (CO-STAR) | pytest: 3 Tests |
| 4 | POST /api/tts (OpenAI onyx) | pytest: 2 Tests |
| 5 | Exchange connect/fetch/disconnect | pytest: 4 Tests |
| 6 | HTML + CSS (Bauhaus, Phil SVG) | Browser |
| 7 | app.js Paste-Modus + TTS + Waveform | Browser |
| 8 | app.js Exchange-Modus | Browser |
| 9 | Dockerfile + docker-compose | Docker |
| 10 | Alle Tests + README | pytest + manuell |

**Gesamt Backend-Tests: 10 pytest-Tests (kein echter API-Call)**
