# webapp/backend/main.py
import io
import json
import os
import re
import time
import uuid
from pathlib import Path

import anthropic
import openai
from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

load_dotenv()

app = FastAPI(title="PHIL PIM Dashboard", version="2.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


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


from backend.exchange_helpers import (
    connect_to_exchange,
    fetch_emails,
    fetch_calendar,
    fetch_tasks,
    complete_task,
    create_task,
    create_calendar_entry,
)

# ── Session-Management (In-Memory) ────────────────────────────────────────
# _sessions: session_id → {account, username, institution}
_sessions: dict[str, dict] = {}

# ── Brute-force-Schutz ────────────────────────────────────────────────────
# _lockout: ip → {attempts, locked_until}
_lockout: dict[str, dict] = {}


def _check_lockout(ip: str):
    """Raises HTTPException(429) wenn IP gesperrt ist."""
    entry = _lockout.get(ip)
    if entry and entry["locked_until"] > time.time():
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Zu viele Fehlversuche.",
                "retry_after": int(entry["locked_until"] - time.time()),
            },
        )


def _record_failure(ip: str):
    """Zählt Fehlversuch, sperrt nach 3 (5 Min) und weiteren (1h)."""
    entry = _lockout.setdefault(ip, {"attempts": 0, "locked_until": 0})
    entry["attempts"] += 1
    if entry["attempts"] >= 4:
        entry["locked_until"] = time.time() + 3600
    elif entry["attempts"] >= 3:
        entry["locked_until"] = time.time() + 300


def _reset_lockout(ip: str):
    _lockout.pop(ip, None)


def _get_account(session_id: str | None):
    """Helper: prüft Session, gibt Account zurück."""
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    return _sessions[session_id]["account"]


class ConnectRequest(BaseModel):
    username: str
    password: str
    institution: str


# ── Auth Endpoints ─────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def auth_login(req: ConnectRequest, request: Request):
    ip = request.client.host
    _check_lockout(ip)
    try:
        account = connect_to_exchange(req.username, req.password, req.institution)
    except Exception:
        _record_failure(ip)
        raise HTTPException(status_code=401, detail="Ungültige Anmeldedaten.")
    _reset_lockout(ip)
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "account": account,
        "username": req.username,
        "institution": req.institution,
    }
    resp = JSONResponse({
        "status": "ok",
        "username": req.username,
        "inbox_count": account.inbox.total_count,
    })
    resp.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="strict",
        secure=False,
    )
    return resp


@app.post("/api/auth/logout")
def auth_logout(session_id: str | None = Cookie(default=None)):
    if session_id:
        _sessions.pop(session_id, None)
    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie("session_id")
    return resp


@app.get("/api/auth/me")
def auth_me(session_id: str | None = Cookie(default=None)):
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=401)
    s = _sessions[session_id]
    return {"username": s["username"], "institution": s["institution"]}


# ── Legacy Exchange Endpoints (kept for backwards compat) ─────────────────

@app.post("/api/exchange/connect")
def exchange_connect(req: ConnectRequest):
    try:
        account = connect_to_exchange(req.username, req.password, req.institution)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Exchange-Verbindung fehlgeschlagen: {e}")

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "account": account,
        "username": req.username,
        "institution": req.institution,
    }

    resp = JSONResponse(content={
        "status": "connected",
        "inbox_count": account.inbox.total_count,
    })
    resp.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="strict",
        secure=False,
    )
    return resp


class FetchRequest(BaseModel):
    max_count: int = 10
    unread_only: bool = True


@app.post("/api/exchange/fetch")
def exchange_fetch(
    req: FetchRequest,
    session_id: str | None = Cookie(default=None),
):
    account = _get_account(session_id)
    emails = fetch_emails(account, max_count=req.max_count, unread_only=req.unread_only)
    skipped = 0
    if emails and "_skipped" in emails[-1]:
        skipped = emails[-1]["_skipped"]
        emails = emails[:-1]
    return {"emails": emails, "skipped": skipped}


@app.post("/api/exchange/disconnect")
def exchange_disconnect(session_id: str | None = Cookie(default=None)):
    if session_id and session_id in _sessions:
        del _sessions[session_id]
    resp = JSONResponse(content={"status": "disconnected"})
    resp.delete_cookie("session_id")
    return resp


# ── Calendar Endpoints ─────────────────────────────────────────────────────

@app.get("/api/calendar")
def get_calendar(
    days_ahead: int = 14,
    session_id: str | None = Cookie(default=None),
):
    account = _get_account(session_id)
    return {"items": fetch_calendar(account, days_ahead)}


class CreateCalendarRequest(BaseModel):
    subject: str
    start: str
    end: str
    location: str = ""
    body: str = ""


@app.post("/api/calendar/create")
def post_create_calendar(
    req: CreateCalendarRequest,
    session_id: str | None = Cookie(default=None),
):
    account = _get_account(session_id)
    return create_calendar_entry(account, req.subject, req.start, req.end, req.location, req.body)


# ── Tasks Endpoints ────────────────────────────────────────────────────────

@app.get("/api/tasks")
def get_tasks(session_id: str | None = Cookie(default=None)):
    account = _get_account(session_id)
    return {"tasks": fetch_tasks(account)}


class CreateTaskRequest(BaseModel):
    subject: str
    due_date: str | None = None
    body: str = ""
    priority: str = "Normal"


@app.post("/api/tasks/create")
def post_create_task(
    req: CreateTaskRequest,
    session_id: str | None = Cookie(default=None),
):
    account = _get_account(session_id)
    return create_task(account, req.subject, req.due_date, req.body, req.priority)


class CompleteTaskRequest(BaseModel):
    changekey: str


@app.post("/api/tasks/{task_id}/complete")
def post_complete_task(
    task_id: str,
    req: CompleteTaskRequest,
    session_id: str | None = Cookie(default=None),
):
    account = _get_account(session_id)
    complete_task(account, task_id, req.changekey)
    return {"status": "completed"}


# ── Phil Chat (SSE Streaming) ──────────────────────────────────────────────

PHIL_SYSTEM = """\
Du bist PHIL, der persönliche KI-Assistent von Prof. Dr. Butscher.
Du kennst seine aktuellen E-Mails, Kalender-Einträge und offenen Aufgaben.
Hilf ihm beim Zeitmanagement, Priorisierung und Planung.
Antworte präzise und freundlich auf Deutsch.
"""


class ChatRequest(BaseModel):
    message: str
    include_context: bool = True


def _build_context(mails: list, cal_items: list, tasks: list) -> str:
    lines = ["=== AKTUELLE SITUATION ==="]
    if mails:
        lines.append(f"\nUngelesene E-Mails ({len(mails)}):")
        for m in mails[:5]:
            lines.append(f"  - Von: {m.get('sender', '?')} | Betreff: {m.get('subject', '?')}")
    if cal_items:
        lines.append(f"\nKalender (nächste 7 Tage, {len(cal_items)} Einträge):")
        for c in cal_items[:5]:
            lines.append(f"  - {c['start'][:10] if c['start'] else '?'}: {c['subject']}")
    if tasks:
        lines.append(f"\nOffene Aufgaben ({len(tasks)}):")
        for t in tasks[:5]:
            due = t["due_date"][:10] if t["due_date"] else "kein Datum"
            lines.append(f"  - {t['subject']} (fällig: {due})")
    return "\n".join(lines)


@app.post("/api/chat")
def chat(req: ChatRequest, session_id: str | None = Cookie(default=None)):
    account = _get_account(session_id)

    context_str = ""
    if req.include_context:
        try:
            mails = fetch_emails(account, max_count=10, unread_only=True)
            if mails and "_skipped" in mails[-1]:
                mails = mails[:-1]
            cal = fetch_calendar(account, days_ahead=7)
            tasks = fetch_tasks(account, max_count=20)
            context_str = _build_context(mails, cal, tasks)
        except Exception:
            context_str = ""

    user_msg = (context_str + "\n\n" + req.message) if context_str else req.message

    def generate():
        with anthropic_client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=PHIL_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {text}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# Frontend statisch servieren
_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
