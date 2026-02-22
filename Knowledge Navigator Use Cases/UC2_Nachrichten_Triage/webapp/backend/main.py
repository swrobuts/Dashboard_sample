# webapp/backend/main.py
import io
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

import anthropic
import openai
import requests as http_client
from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

load_dotenv()
load_dotenv(Path(__file__).parent / ".env", override=False)

from backend.knowledge_store import KnowledgeStore
from backend.ontology_store import OntologyStore
from backend.attachment_extractor import extract_text as extract_attachment_text

try:
    knowledge_store = KnowledgeStore()
except ValueError as e:
    logging.warning(f"[RAG] KnowledgeStore deaktiviert (kein API-Key): {e}")
    knowledge_store = None
except Exception as e:
    logging.warning(f"[RAG] KnowledgeStore deaktiviert (unerwarteter Fehler): {type(e).__name__}: {e}")
    knowledge_store = None

try:
    ontology_store = OntologyStore()
except Exception as e:
    logging.warning(f"[Ontology] OntologyStore deaktiviert: {type(e).__name__}: {e}")
    ontology_store = None

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
    "empfohlene_aktion": "Konkrete, sofort umsetzbare Empfehlung.",
    "stimmung": <Zahl von -1.0 bis 1.0; sehr negativ=-1, neutral=0, sehr positiv=1>
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


def _parse_sender(sender: str) -> tuple[str, str]:
    """Extract (name, email) from 'Name <email>' or plain email string."""
    m = re.match(r'^["\']?([^<"\']+?)["\']?\s*<([^>]+)>', sender.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    if "@" in sender:
        return sender.strip(), sender.strip()
    return sender.strip(), ""


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
        return {k: data.get(k, []) for k in _EMPTY}
    except Exception as exc:
        logging.warning(f"[Ontology] Entity-Extraktion fehlgeschlagen: {exc}")
        return _EMPTY


class AttachmentIn(BaseModel):
    filename: str
    mime_type: str
    data_b64: str   # base64-encoded bytes


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

    return result


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
    INSTITUTIONS,
    build_email_text,
    complete_task,
    connect_to_exchange,
    connect_to_exchange_thws,
    connect_to_imap,
    create_google_calendar_event,
    create_task,
    delete_task,
    fetch_google_calendar,
    fetch_emails,
    fetch_emails_imap,
    fetch_tasks,
)

# ── Session-Management (In-Memory) ────────────────────────────────────────
# _sessions: session_id → {protocol, username, institution, ...}
#   IMAP: {protocol:"imap", imap_config:{host,port,username,password,inbox_count}, ...}
#   EWS:  {protocol:"ews",  account:<Account>, ...}
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


def _get_session(session_id: str | None) -> dict:
    """Helper: prüft Session, gibt Session-Dict zurück."""
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    return _sessions[session_id]


def _get_account(session_id: str | None):
    """Helper: gibt EWS-Account zurück.
    - 'ews': account direkt
    - 'imap+ews': account wenn EWS-Login erfolgreich war, sonst 400
    - 'imap': kein EWS, 400
    """
    session = _get_session(session_id)
    account = session.get("account")
    if account is None:
        raise HTTPException(
            status_code=400,
            detail="Kalender/Aufgaben nicht verfügbar (kein EWS-Zugang für diese Institution).",
        )
    return account


class ConnectRequest(BaseModel):
    username: str
    password: str
    institution: str
    exchange_email: str | None = None  # optionale E-Mail für EWS primary_smtp


# ── Auth Endpoints ─────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def auth_login(req: ConnectRequest, request: Request):
    ip = request.client.host
    _check_lockout(ip)
    inst = INSTITUTIONS.get(req.institution, {})
    protocol = inst.get("protocol", "ews")
    try:
        if protocol == "imap+ews":
            # THWS: IMAP für E-Mail (Pflicht), EWS für Kalender/Aufgaben (optional)
            result = connect_to_imap(
                req.username, req.password,
                inst["imap_host"], inst["imap_port"],
            )
            inbox_count = result["inbox_count"]
            _email = req.exchange_email or ""
            _fn = _email.split("@")[0].split(".")[0].capitalize() if "@" in _email else req.username.capitalize()
            session_data = {
                "protocol": "imap+ews",
                "imap_config": result,
                "username": result["username"],
                "first_name": _fn,
                "institution": req.institution,
                "account": None,  # wird unten befüllt wenn EWS klappt
            }
            # EWS-Verbindung für Kalender/Aufgaben — optional, Fehler werden geloggt
            try:
                ews_account = connect_to_exchange_thws(
                    req.username, req.password, exchange_email=req.exchange_email
                )
                session_data["account"] = ews_account
                session_data["ews_error"] = None
            except Exception as ews_exc:
                logging.warning(f"[EWS] THWS Verbindung fehlgeschlagen: {type(ews_exc).__name__}: {ews_exc}")
                session_data["ews_error"] = f"{type(ews_exc).__name__}: {str(ews_exc)[:300]}"
        elif protocol == "imap":
            result = connect_to_imap(
                req.username, req.password,
                inst["imap_host"], inst["imap_port"],
            )
            inbox_count = result["inbox_count"]
            session_data = {
                "protocol": "imap",
                "imap_config": result,
                "username": result["username"],
                "first_name": req.username.capitalize(),
                "institution": req.institution,
                "account": None,
            }
        else:
            account = connect_to_exchange(req.username, req.password, req.institution)
            # inbox.total_count ist der erste echte EWS-Call — Authentifizierung passiert hier
            inbox_count = account.inbox.total_count
            try:
                unread_count = account.inbox.unread_count
            except Exception:
                unread_count = 0
            try:
                drafts_count = account.drafts.total_count
            except Exception:
                drafts_count = 0
            try:
                from datetime import date as _date
                from exchangelib import EWSTimeZone, EWSDateTime
                _tz = EWSTimeZone.localzone()
                _today = _date.today()
                _start = EWSDateTime(_today.year, _today.month, _today.day, 0, 0, 0, tzinfo=_tz)
                sent_today = sum(1 for _ in account.sent.filter(datetime_sent__gte=_start).only("id"))
            except Exception:
                sent_today = 0
            session_data = {
                "protocol": "ews",
                "account": account,
                "username": req.username,
                "first_name": req.username.split(".")[0].capitalize(),
                "institution": req.institution,
                "inbox_count": inbox_count,
                "unread_count": unread_count,
                "drafts_count": drafts_count,
                "sent_today": sent_today,
            }
    except Exception as e:
        import traceback; traceback.print_exc()
        _record_failure(ip)
        raise HTTPException(status_code=401, detail=f"Verbindung fehlgeschlagen: {type(e).__name__}: {e}")
    _reset_lockout(ip)
    session_id = str(uuid.uuid4())
    _sessions[session_id] = session_data
    resp = JSONResponse({
        "status": "ok",
        "username": session_data["username"],
        "first_name": session_data.get("first_name", session_data["username"]),
        "institution": session_data["institution"],
        "inbox_count": inbox_count,
        "unread_count": session_data.get("unread_count", 0),
        "drafts_count": session_data.get("drafts_count", 0),
        "sent_today": session_data.get("sent_today", 0),
        "ews_connected": session_data.get("account") is not None,
        "ews_error": session_data.get("ews_error"),
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
    imap_cfg = s.get("imap_config") or {}
    return {
        "username": s["username"],
        "first_name": s.get("first_name", s["username"]),
        "institution": s["institution"],
        "ews_connected": s.get("account") is not None,
        "ews_error": s.get("ews_error"),
        "inbox_count": s.get("inbox_count", imap_cfg.get("inbox_count", 0)),
        "unread_count": s.get("unread_count", 0),
        "drafts_count": s.get("drafts_count", 0),
        "sent_today": s.get("sent_today", 0),
    }


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
        "protocol": "ews",
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
    session = _get_session(session_id)
    if "imap_config" in session:
        # THWS (imap+ews) oder reines IMAP — E-Mails immer via IMAP
        emails = fetch_emails_imap(session["imap_config"], max_count=req.max_count, unread_only=req.unread_only)
    else:
        emails = fetch_emails(session["account"], max_count=req.max_count, unread_only=req.unread_only)
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
    _get_session(session_id)  # nur Login-Check; Kalender kommt von Google
    try:
        return {"items": fetch_google_calendar(days_ahead)}
    except Exception as e:
        logging.warning(f"[GCal] {e}")
        raise HTTPException(status_code=502, detail=f"Google Calendar: {e}")


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
    _get_session(session_id)
    try:
        return create_google_calendar_event(req.subject, req.start, req.end, req.location, req.body)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Google Calendar create: {e}")


# ── Tasks Endpoints ────────────────────────────────────────────────────────

@app.get("/api/tasks")
def get_tasks(session_id: str | None = Cookie(default=None)):
    session = _get_session(session_id)
    account = session.get("account")
    if account is None:
        return {"tasks": []}
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


class DeleteTaskRequest(BaseModel):
    changekey: str


@app.delete("/api/tasks/{task_id}")
def post_delete_task(
    task_id: str,
    req: DeleteTaskRequest,
    session_id: str | None = Cookie(default=None),
):
    account = _get_account(session_id)
    delete_task(account, task_id, req.changekey)
    return {"status": "deleted"}


# ── Phil Chat (SSE Streaming) ──────────────────────────────────────────────

PHIL_SYSTEM = """\
Du bist PHIL, der persönliche KI-Assistent von Prof. Dr. Butscher.
Du kennst seine aktuellen E-Mails, Kalender-Einträge und offenen Aufgaben.
Hilf ihm beim Zeitmanagement, Priorisierung und Planung.

Antworte IMMER auf Deutsch.
Halte Antworten kurz und präzise — maximal 3–4 Sätze.
Keine unnötigen Einleitungen, keine Zusammenfassungen am Ende.
Direkt zur Sache.
"""


class ChatRequest(BaseModel):
    message: str
    include_context: bool = True


def _build_rag_context(query: str) -> str:
    """Retrieve semantically similar past mails and format as context block."""
    if knowledge_store is None:
        return ""
    try:
        results = knowledge_store.search(query, n_results=3)
    except Exception as exc:
        logging.warning(f"[RAG] Suche fehlgeschlagen: {exc}")
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


def _build_context(mails: list, cal_items: list, tasks: list) -> str:
    lines = ["=== AKTUELLE SITUATION ==="]
    if mails:
        lines.append(f"\nUngelesene E-Mails ({len(mails)}):")
        for m in mails[:10]:
            lines.append(f"  - Von: {m.get('sender', '?')} | Betreff: {m.get('subject', '?')}")
    else:
        lines.append("\nUngelesene E-Mails: keine")
    if cal_items:
        lines.append(f"\nKalender (nächste 7 Tage, {len(cal_items)} Einträge):")
        for c in cal_items:
            start = c.get("start") or ""
            date = start[:10] if start else "?"
            time = start[11:16] if len(start) > 10 else ""
            loc = f" | Ort: {c['location']}" if c.get("location") else ""
            lines.append(f"  - {date} {time}: {c['subject']}{loc}")
    else:
        lines.append("\nKalender: keine Einträge in den nächsten 7 Tagen")
    if tasks:
        lines.append(f"\nOffene Aufgaben ({len(tasks)}):")
        for t in tasks:
            due = t["due_date"][:10] if t.get("due_date") else "kein Datum"
            prio = t.get("priority", "Normal")
            status = t.get("status", "NotStarted")
            lines.append(f"  - [{prio}] {t['subject']} (fällig: {due}, Status: {status})")
    else:
        lines.append("\nOffene Aufgaben: keine")
    return "\n".join(lines)


@app.post("/api/chat")
def chat(req: ChatRequest, session_id: str | None = Cookie(default=None)):
    session = _get_session(session_id)

    context_str = ""
    if req.include_context:
        # Each source is fetched independently — a single failure won't kill the entire context
        try:
            if "imap_config" in session:
                mails: list = fetch_emails_imap(session["imap_config"], max_count=10, unread_only=True)
            else:
                account_for_mail = session.get("account")
                raw = fetch_emails(account_for_mail, max_count=10, unread_only=True) if account_for_mail else []
                mails = [m for m in raw if "_skipped" not in m]
        except Exception as exc:
            logging.warning(f"[Chat-Ctx] Mails fehlgeschlagen: {exc}")
            mails = []
        try:
            cal: list = fetch_google_calendar(days_ahead=7)
        except Exception as exc:
            logging.warning(f"[Chat-Ctx] Kalender fehlgeschlagen: {exc}")
            cal = []
        try:
            account = session.get("account")
            tasks: list = fetch_tasks(account, max_count=50) if account else []
        except Exception as exc:
            logging.warning(f"[Chat-Ctx] Aufgaben fehlgeschlagen: {exc}")
            tasks = []
        context_str = _build_context(mails, cal, tasks)
        logging.warning(f"[Chat-Ctx] Kontext: {len(mails)} Mails, {len(cal)} Kalender, {len(tasks)} Aufgaben")

        # RAG: enrich with semantically similar past mails
        rag_str = _build_rag_context(req.message)
        if rag_str:
            context_str += rag_str

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


# ── Graph / Knowledge-Map ──────────────────────────────────────────────────────
class GraphRequest(BaseModel):
    subject: str
    text: str  # content to analyze (mail body, event description, task body)


@app.post("/api/graph")
def get_graph(req: GraphRequest, session_id: str | None = Cookie(default=None)):
    """Extracts a knowledge graph (nodes + edges) from text using Claude."""
    _get_session(session_id)
    import re, json as _json

    prompt = f"""Analysiere den folgenden Text und erstelle einen strukturierten Wissensgraphen.

Antworte NUR mit einem validen JSON-Objekt (keine Erklärungen, kein Markdown), exakt diese Struktur:
{{
  "nodes": [
    {{"id": "center", "label": "<Hauptthema max. 4 Wörter>", "type": "center"}},
    {{"id": "n1", "label": "<Label max. 3 Wörter>", "type": "<typ>"}}
  ],
  "edges": [
    {{"source": "center", "target": "n1", "label": "<Beziehung 1-2 Wörter>"}}
  ]
}}

Erlaubte Typen: person, thema, datum, ort, aktion, organisation
Maximal 10 Knoten (inkl. center). Labels kurz. Nur die wichtigsten Entitäten.

Thema: {req.subject}
Text:
{req.text[:3000]}"""

    response = anthropic_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Extract JSON — handle potential markdown code fences
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return _json.loads(match.group())
        except Exception:
            pass
    # Fallback: minimal graph
    return {
        "nodes": [{"id": "center", "label": req.subject[:30], "type": "center"}],
        "edges": [],
    }


# ── DB HAFAS Train Planner (via pyHafas + NVV profile) ──────────────────────

from pyhafas import HafasClient
from pyhafas.profile import NVVProfile
from pyhafas.types.fptf import Station as HafasStation
from datetime import timezone as _tz

_hafas = HafasClient(NVVProfile())


@app.get("/api/trains/stations")
def train_stations(q: str, session_id: str | None = Cookie(default=None)):
    """Bahnhofsuche via DB HAFAS (NVV-Profil)."""
    _get_session(session_id)
    try:
        stations = _hafas.locations(q)
    except Exception as e:
        raise HTTPException(502, detail=f"HAFAS nicht erreichbar: {e}")
    return {"stations": [
        {"id": s.id, "name": s.name}
        for s in stations[:7]
        if s.id and s.name
    ]}


@app.get("/api/trains/journeys")
def train_journeys(
    from_id: str,
    to_id: str,
    when: str = "",
    results: int = 5,
    session_id: str | None = Cookie(default=None),
):
    """Verbindungssuche via DB HAFAS (NVV-Profil)."""
    _get_session(session_id)
    origin = HafasStation(id=from_id, name="")
    destination = HafasStation(id=to_id, name="")
    dep_dt = None
    if when:
        from datetime import datetime as _dt
        dep_dt = _dt.fromisoformat(when).replace(tzinfo=_tz.utc)
    try:
        raw = _hafas.journeys(
            origin=origin,
            destination=destination,
            date=dep_dt,
            max_journeys=results,
            max_changes=-1,
        )
    except Exception as e:
        raise HTTPException(502, detail=f"HAFAS nicht erreichbar: {e}")

    journeys = []
    for j in raw:
        if not j.legs:
            continue
        first, last = j.legs[0], j.legs[-1]
        dep = first.departure.isoformat() if first.departure else None
        arr = last.arrival.isoformat() if last.arrival else None
        delay_dep = (first.departureDelay or 0)
        delay_arr = (last.arrivalDelay or 0)
        real_legs = [lg for lg in j.legs if not getattr(lg, "walking", False)]
        changes = max(len(real_legs) - 1, 0)
        products = [lg.name for lg in real_legs if lg.name]
        journeys.append({
            "departure": dep,
            "arrival": arr,
            "delay_dep": int(delay_dep.total_seconds() // 60) if hasattr(delay_dep, "total_seconds") else int((delay_dep or 0) // 60),
            "delay_arr": int(delay_arr.total_seconds() // 60) if hasattr(delay_arr, "total_seconds") else int((delay_arr or 0) // 60),
            "changes": changes,
            "products": products,
            "price": None,
        })
    return {"journeys": journeys}


# ── Knowledge Search (RAG) ────────────────────────────────────────────────

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
    if knowledge_store is None:
        return {"results": []}
    results = knowledge_store.search(q.strip(), n_results=min(n, 10))
    return {"results": results}


# Frontend statisch servieren (React build → static/)
_static = Path(__file__).parent.parent / "static"
if _static.exists():
    # Serve JS/CSS chunks
    _assets = _static / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    from fastapi.responses import FileResponse

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str = ""):
        # Serve real static files (png, svg, ico, txt, …) directly
        if full_path:
            candidate = _static / full_path
            if candidate.is_file():
                return FileResponse(str(candidate))
        index = _static / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return {"error": "Frontend not built. Run: cd frontend && npm run build"}
