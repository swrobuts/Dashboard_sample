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
from pydantic import BaseModel, field_validator, model_validator

load_dotenv()
load_dotenv(Path(__file__).parent / ".env", override=False)

from backend.knowledge_store import KnowledgeStore
from backend.ontology_store import OntologyStore
from backend.attachment_extractor import extract_text as extract_attachment_text
from backend.llm_client import get_llm_client
from backend.memory_store import MemoryStore
from backend.web_search import WEB_SEARCH_TRIGGER_RE, build_web_context
TRAIN_TRIGGER_RE = re.compile(
    r'\b(zug|züge|bahn|verbindung|fahrplan|fahren nach|reisen nach|bahnhof|'
    r'ICE|IC\b|regional|db\.de|bahn\.de|abfahrt|ankunft|umsteigen|gleis|'
    r'wann fährt|welche verbindung|nächster zug)\b',
    re.IGNORECASE,
)

try:
    # ChromaDB uses memory-mapped HNSW files — must NOT live in OneDrive (causes SIGBUS).
    # Store under /tmp so OneDrive never touches these files.
    knowledge_store = KnowledgeStore(persist_path="/tmp/phil_chroma")
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

_MEMORY_DB_PATH = str(Path(__file__).parent.parent / "data" / "memory.db")

try:
    memory_store = MemoryStore(
        db_path=_MEMORY_DB_PATH,
        chroma_path="/tmp/phil_chroma",
    )
    logging.info("[Memory] MemoryStore initialisiert")
except Exception as e:
    logging.warning(f"[Memory] MemoryStore deaktiviert: {type(e).__name__}: {e}")
    memory_store = None

app = FastAPI(title="PHIL PIM Dashboard", version="2.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/health/llm")
def health_llm(mode: str = "local"):
    """Prüft ob der gewählte LLM-Provider erreichbar ist."""
    llm = get_llm_client(mode)
    return llm.check_health()


anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# ── LLM-Client für Session ────────────────────────────────────────────────
# Der globale anthropic_client bleibt für Abwärtskompatibilität bestehen.
# Neue Aufrufe nutzen _get_llm(session) → wählt Cloud/Local/Hybrid je nach Session.

def _get_llm(session: dict | None = None):
    """Gibt den LLM-Client für die aktuelle Session zurück.

    Falls keine Session (z.B. Legacy-Endpoints), wird der Cloud-Client verwendet.
    """
    if session is None:
        return get_llm_client("cloud")
    return get_llm_client(session.get("llm_mode", "cloud"))


def _llm_create(llm, *, task: str, prompt: str, max_tokens: int = 512, system: str | None = None) -> str:
    """Ruft llm.create() auf — fällt bei lokalem Ausfall automatisch auf Cloud zurück."""
    try:
        return llm.create(task=task, prompt=prompt, max_tokens=max_tokens, system=system)
    except Exception as exc:
        if getattr(llm, 'mode', 'cloud') != 'cloud':
            logging.warning(f"[LLM] '{llm.mode}' nicht erreichbar ({type(exc).__name__}), Fallback auf Cloud.")
            return get_llm_client("cloud").create(task=task, prompt=prompt, max_tokens=max_tokens, system=system)
        raise

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


def _summarize_attachment(filename: str, text: str, llm=None) -> str:
    """Summarize attachment in 3 sentences using the configured LLM."""
    if llm is None:
        llm = get_llm_client("cloud")
    prompt = (
        f"Fasse den folgenden Anhang '{filename}' in maximal 3 Sätzen zusammen:\n\n"
        f"{text[:3000]}"
    )
    try:
        return llm.create(task="attachment_summary", prompt=prompt, max_tokens=256).strip()
    except Exception as exc:
        logging.warning(f"[Attachment] Zusammenfassung fehlgeschlagen: {exc}")
        return ""


def _extract_entities(mail_text: str, llm=None) -> dict:
    """Extract structured entities from mail text using the configured LLM.

    Returns dict with keys: persons, projects, deadlines, action_items.
    Returns empty lists on any error — never raises.
    """
    if llm is None:
        llm = get_llm_client("cloud")
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
        raw = _strip_fences(_llm_create(llm, task="entities", prompt=prompt, max_tokens=512))
        data = json.loads(raw)
        return {k: data.get(k, []) for k in _EMPTY}
    except Exception as exc:
        logging.warning(f"[Ontology] Entity-Extraktion fehlgeschlagen: {exc}")
        return _EMPTY


_MAX_ATTACHMENT_B64 = 13_631_488  # ~10 MB decoded (base64 overhead ≈ 4/3)
_MAX_ATTACHMENTS = 10


class AttachmentIn(BaseModel):
    filename: str
    mime_type: str
    data_b64: str   # base64-encoded bytes

    @field_validator("data_b64")
    @classmethod
    def size_limit(cls, v: str) -> str:
        if len(v) > _MAX_ATTACHMENT_B64:
            raise ValueError(f"Anhang zu groß (max 10 MB).")
        return v


class AnalyzeRequest(BaseModel):
    email_text: str
    mail_id: str | None = None
    subject: str = ""
    sender: str = ""
    date: str = ""
    attachments: list[AttachmentIn] = []

    @field_validator("attachments")
    @classmethod
    def max_attachments(cls, v: list) -> list:
        if len(v) > _MAX_ATTACHMENTS:
            raise ValueError(f"Maximal {_MAX_ATTACHMENTS} Anhänge erlaubt.")
        return v

    @field_validator("email_text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("email_text darf nicht leer sein")
        return v


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, session_id: str | None = Cookie(default=None)):
    import base64

    # ── LLM-Client für diese Session ──────────────────────────────────
    session = _sessions.get(session_id) if session_id else None
    llm = _get_llm(session)

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
        raw_text = _llm_create(llm, task="triage", prompt=prompt, max_tokens=512)
    except anthropic.APIStatusError as e:
        status = e.status_code if hasattr(e, "status_code") else 500
        if status == 529 or status == 429:
            raise HTTPException(status_code=503, detail="KI-Dienst vorübergehend ausgelastet. Bitte kurz warten.")
        raise HTTPException(status_code=502, detail=f"LLM API Fehler: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM Fehler: {type(e).__name__}: {e}")
    raw = _strip_fences(raw_text)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"LLM-Antwort kein gültiges JSON: {e}")

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
            att_summary = _summarize_attachment(att.filename, att_text, llm=llm)
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
            entities = _extract_entities(req.email_text, llm=llm)
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
    delete_google_calendar_event,
    update_google_calendar_event,
    delete_mail_imap,
    delete_mail_ews,
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
    llm_mode: str = "cloud"  # "cloud" | "hybrid" | "local"

    @field_validator("llm_mode")
    @classmethod
    def valid_llm_mode(cls, v: str) -> str:
        if v not in ("cloud", "hybrid", "local"):
            return "cloud"
        return v


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
                "llm_mode": req.llm_mode,
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
                "llm_mode": req.llm_mode,
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
                "llm_mode": req.llm_mode,
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
        "llm_mode": session_data.get("llm_mode", "cloud"),
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
        "llm_mode": s.get("llm_mode", "cloud"),
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
    try:
        delete_task(account, task_id, req.changekey)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Löschen fehlgeschlagen: {exc}")
    return {"status": "deleted"}


# ── Mail Delete Endpoint ───────────────────────────────────────────────────

@app.delete("/api/mails/{mail_uid}")
def delete_mail_endpoint(
    mail_uid: str,
    session_id: str | None = Cookie(default=None),
):
    """Löscht eine E-Mail dauerhaft vom Server (IMAP oder EWS)."""
    session = _get_session(session_id)
    if "imap_config" in session:
        delete_mail_imap(session["imap_config"], mail_uid)
    else:
        account = session.get("account")
        if account:
            delete_mail_ews(account, mail_uid)
    return {"status": "deleted"}


# ── Calendar Delete Endpoint ───────────────────────────────────────────────

class UpdateCalendarRequest(BaseModel):
    subject: str
    start: str
    end: str
    location: str = ""
    body: str = ""


@app.patch("/api/calendar/{event_id}")
def patch_calendar_endpoint(
    event_id: str,
    req: UpdateCalendarRequest,
    session_id: str | None = Cookie(default=None),
):
    """Aktualisiert einen Kalender-Eintrag (Google Calendar via gog CLI)."""
    _get_session(session_id)
    try:
        return update_google_calendar_event(
            event_id, req.subject, req.start, req.end, req.location, req.body
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Kalender-Update fehlgeschlagen: {e}")


class DeleteCalendarRequest(BaseModel):
    changekey: str = ""


@app.delete("/api/calendar/{event_id}")
def delete_calendar_endpoint(
    event_id: str,
    req: DeleteCalendarRequest,
    session_id: str | None = Cookie(default=None),
):
    """Löscht einen Kalender-Eintrag (Google Calendar via gog CLI)."""
    _get_session(session_id)
    try:
        delete_google_calendar_event(event_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Kalender-Löschen fehlgeschlagen: {e}")
    return {"status": "deleted"}


# ── Phil Chat (SSE Streaming) ──────────────────────────────────────────────

PHIL_SYSTEM = """\
Du bist PHIL — der smarte, proaktive persönliche Assistent von Prof. Dr. Butscher.
Du bist neugierig, direkt und denkst einen Schritt voraus.

## Wie du denkst

Wenn du einen Termin, eine Mail oder Aufgabe siehst und dir der Kontext unklar ist
(kryptischer Name, unbekanntes Projekt, unklarer Zweck):
→ Frage EINMAL kurz und gezielt nach: „Was ist [X]? Kurz recherchieren?"

Sobald du weißt, worum es geht — denke SOFORT praktisch-konkret aus der Domäne:
  - Getränkelieferung? → Leergut bereitstellen, Zugang klären, Zahlung vorbereiten
  - Arzttermin? → Versicherungskarte, Beschwerden notiert, ggf. nüchtern kommen
  - Zoom-Call? → Link testen, Kamera/Mikro prüfen, Unterlagen griffbereit
  - Gastdozent kommt? → Raum, Beamer, WLAN-Zugang, Parkplatz kommunizieren
  - Prüfungsausschuss? → Unterlagen, Protokoll, Beschlüsse vorbereiten

Nicht: „Überlegen Sie sich die Ziele des Meetings" — das ist wertlos.
Ja: Die 2–4 physischen/konkreten Dinge, die er wirklich tun muss.

## Was du tust

- Schlage proaktiv nächste Schritte vor, ohne darauf zu warten, gefragt zu werden.
- Gib eigene Einschätzung: Ist das dringend? Fehlt etwas? Klingt die Mail schwierig?
- Biete konkrete Aktionen an: Antwort entwerfen, Erinnerung anlegen, Aufgabe erstellen.
- Wiederhole NICHT, was er selbst im Termintext liest. Füge Mehrwert hinzu.
- Wenn du etwas Neues über seine Welt lernst (Person, Projekt, Kontext), merke es dir
  mit: „Ich merke mir: [Fakt]" — am Ende deiner Antwort, eine Zeile, kein Aufhebens.

Antworte auf Deutsch. Prägnant, direkt, kein Bullshit. Länge: so viel wie nötig.
"""


class ChatRequest(BaseModel):
    message: str
    include_context: bool = True
    message_id: str = ""  # uuid4 from frontend; used to tag extracted facts


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


def _build_graph_context(query: str) -> str:
    """Get structured knowledge graph context block from the ontology."""
    if ontology_store is None:
        return ""
    try:
        return ontology_store.get_context_for_chat(query)
    except Exception as exc:
        logging.warning(f"[Ontology] Graph-Kontext fehlgeschlagen: {exc}")
        return ""


FACT_EXTRACTION_SYSTEM = """\
Extrahiere aus diesem Gespräch maximal 3 neue, konkrete Fakten über Personen,
Projekte, Konzepte, Orte oder Abläufe.
Nur wirklich neue Informationen — keine allgemeinen Aussagen.
Antworte ausschließlich mit validem JSON (kein Markdown):
[{"text": "...", "category": "Person|Projekt|Konzept|Prozedur|Ort", "confidence": 0.7}]
Wenn keine neuen Fakten: []
"""


def _extract_and_store_facts(user_msg: str, phil_response: str, message_id: str) -> None:
    """Async fact extraction after chat response. Errors are swallowed — non-blocking."""
    if memory_store is None:
        return
    try:
        llm = get_llm_client("cloud")
        prompt = f"[Nutzer]: {user_msg[:400]}\n[Phil]: {phil_response[:800]}"
        raw = llm.create(task="entities", prompt=prompt, max_tokens=256, system=FACT_EXTRACTION_SYSTEM)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        facts = json.loads(raw.strip())
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


_CAL_STOP_WORDS = {
    # Articles, pronouns, prepositions
    "was", "ist", "hat", "der", "die", "das", "und", "mit", "von", "für",
    "mir", "mich", "mein", "meine", "alle", "wann", "welche", "welcher",
    "gibt", "haben", "hatte", "gab", "nächste", "nächsten", "letzten",
    "du", "ich", "wir", "sie", "zu", "bei", "seit", "bis", "über", "mal",
    "bitte", "zeig", "zeige", "such", "suche", "finde", "jeden", "auch",
    "oder", "aber", "wenn", "dann", "noch", "schon", "doch", "nur",
    # Generic nouns / verbs that appear in queries but not in event titles
    "liste", "termin", "termine", "aufgabe", "aufgaben", "kalender",
    "heute", "morgen", "gestern", "uhrzeit", "datum", "monat", "jahr",
    "arbeiten", "akribisch", "genau", "komplett", "vollständig",
}


def _cal_format(c: dict) -> str:
    start = c.get("start") or ""
    date = start[:10] if start else "?"
    time = start[11:16] if len(start) > 10 else ""
    loc = f" | Ort: {c['location']}" if c.get("location") else ""
    body_hint = f" | {c['body'][:60]}…" if c.get("body") and len(c.get("body", "")) > 10 else ""
    return f"  - {date} {time}: {c['subject']}{loc}{body_hint}"


def _calendar_keywords(query: str) -> set[str]:
    """Extract meaningful entity keywords (names, places, topics) from a user query.

    Uses minimum length 5 to avoid matching common short German function words
    that appear in event descriptions and would cause too many false positives.
    """
    return {
        w.lower().strip("?!.,;:-_\"'()")
        for w in query.split()
        if len(w) >= 5 and w.lower().strip("?!.,;:-_\"'()") not in _CAL_STOP_WORDS
    }


def _build_context(mails: list, cal_items: list, tasks: list, cal_query: str = "") -> str:
    lines = ["=== AKTUELLE SITUATION ==="]
    if mails:
        lines.append(f"\nUngelesene E-Mails ({len(mails)}):")
        for m in mails[:10]:
            lines.append(f"  - Von: {m.get('sender', '?')} | Betreff: {m.get('subject', '?')}")
    else:
        lines.append("\nUngelesene E-Mails: keine")

    today = datetime.now(timezone.utc).date().isoformat()

    # If the query contains specific keywords, prepend a dedicated search-result block
    # that lists ALL matching events (past + future) from the full date range.
    # This prevents the LLM from hallucinating or mixing memory with calendar data.
    if cal_query:
        kws = _calendar_keywords(cal_query)
        matched_all = [
            c for c in cal_items
            if any(kw in f"{c.get('subject', '')} {c.get('location', '')} {c.get('body', '')}".lower()
                   for kw in kws)
        ]
        if matched_all:
            lines.append(
                f"\n=== KALENDERSUCHE: VOLLSTÄNDIGE TREFFERLISTE ==="
                f"\n(Abfrage: \"{cal_query[:80]}\" | {len(matched_all)} Treffer aus {len(cal_items)} Einträgen"
                f" — dies ist die autoritative Quelle; zähle NUR diese Einträge)"
            )
            for c in matched_all:
                lines.append(_cal_format(c))
            lines.append("=== ENDE KALENDERSUCHE ===")

    # Regular upcoming calendar — limit to next 14 days to keep context lean
    cutoff_14 = (datetime.now(timezone.utc).date() + timedelta(days=14)).isoformat()
    upcoming_14 = [c for c in cal_items if today <= (c.get("start") or "")[:10] <= cutoff_14]
    if upcoming_14:
        lines.append(f"\nKalender — nächste 14 Tage ({len(upcoming_14)} Einträge):")
        for c in upcoming_14:
            lines.append(_cal_format(c))
    else:
        lines.append("\nKalender: keine Einträge in den nächsten 14 Tagen")

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
            cal: list = fetch_google_calendar(days_ahead=365, days_behind=180)
        except Exception as exc:
            logging.warning(f"[Chat-Ctx] Kalender fehlgeschlagen: {exc}")
            cal = []
        try:
            account = session.get("account")
            tasks: list = fetch_tasks(account, max_count=50) if account else []
        except Exception as exc:
            logging.warning(f"[Chat-Ctx] Aufgaben fehlgeschlagen: {exc}")
            tasks = []
        context_str = _build_context(mails, cal, tasks, cal_query=req.message)
        logging.warning(f"[Chat-Ctx] Kontext: {len(mails)} Mails, {len(cal)} Kalender, {len(tasks)} Aufgaben")

        # RAG: enrich with semantically similar past mails
        rag_str = _build_rag_context(req.message)
        if rag_str:
            context_str += rag_str

        # Ontology: enrich with structured knowledge graph
        graph_str = _build_graph_context(req.message)
        if graph_str:
            context_str += graph_str

    # Memory context: always inject relevant facts (regardless of include_context)
    if memory_store is not None:
        try:
            memory_str = memory_store.build_context_block(req.message)
            if memory_str:
                context_str += memory_str
        except Exception as exc:
            logging.warning(f"[Memory] Kontext fehlgeschlagen: {exc}")

    # Web search: trigger on keywords in user message
    if WEB_SEARCH_TRIGGER_RE.search(req.message):
        try:
            web_str, web_results = build_web_context(req.message)
            if web_str:
                context_str += web_str
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

    user_msg = (context_str + "\n\n" + req.message) if context_str else req.message

    # ── LLM-Client für diese Session ──────────────────────────────────
    llm = _get_llm(session)

    # Train: detect and embed NAV token for frontend navigation
    if TRAIN_TRIGGER_RE.search(req.message):
        try:
            _train_nav = _build_train_nav(req.message, llm)
            if _train_nav:
                user_msg += (
                    f"\n\n[Systeminformation: Zugverbindung wurde abgerufen. "
                    f"Füge am Ende deiner Antwort diesen Token exakt ein (ohne Änderungen): {_train_nav}]"
                )
        except Exception as exc:
            logging.warning(f"[Train] NAV fehlgeschlagen: {exc}")

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
        # Async fact extraction after response is complete (skip if LLM errored out)
        if _full_response:
            _extract_and_store_facts(req.message, "".join(_full_response), req.message_id)
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Meeting Briefing (UC3) ────────────────────────────────────────────────────
class BriefingRequest(BaseModel):
    subject: str
    start: str = ""
    end: str = ""
    location: str = ""
    body: str = ""


class MemoryFeedbackRequest(BaseModel):
    fact_id: str
    rating: str  # "up" | "down"

class MemoryUpdateRequest(BaseModel):
    text: str | None = None
    correction_note: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "MemoryUpdateRequest":
        if self.text is None and self.correction_note is None:
            raise ValueError("Mindestens eines der Felder 'text' oder 'correction_note' muss angegeben werden.")
        return self


BRIEFING_SYSTEM = """\
Du bist PHIL, der persönliche KI-Assistent von Prof. Dr. Butscher.
Erstelle ein kompaktes Meeting-Briefing auf Deutsch.
Verwende EXAKT diese Markdown-Struktur, keine Abweichungen:

## 👤 Teilnehmer
<Namen aus dem Termin, oder "Keine erkannt">

## 📬 Letzte Mails
<Relevante Mails aus dem Kontext mit Datum, oder "Keine gefunden.">

## 📋 Agenda-Vorschlag
<3–5 konkrete Punkte basierend auf Termin und Mails>

Sei prägnant. Maximal 200 Wörter insgesamt. Kein Einleitungssatz.
"""


@app.post("/api/briefing")
def briefing(req: BriefingRequest, session_id: str | None = Cookie(default=None)):
    """Erstellt ein Meeting-Briefing: Teilnehmer, Mails, Agenda (SSE streaming)."""
    session = _get_session(session_id)
    llm = _get_llm(session)

    # 1. Person aus Betreff extrahieren
    person_match = re.search(
        r'\bmit\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)+)',
        req.subject,
        re.IGNORECASE,
    )
    person_name = person_match.group(1) if person_match else None

    # 2. RAG-Suche nach ähnlichen Mails
    rag_lines: list[str] = []
    rag_query = f"{person_name} {req.subject}" if person_name else req.subject
    if knowledge_store is not None:
        try:
            results = knowledge_store.search(rag_query, n_results=5)
            for r in results:
                if r.get("score", 0) >= 0.60:
                    rag_lines.append(
                        f"  [{r['date']}] Von: {r['sender']} | Betreff: {r['subject']}"
                        f" | Relevanz: {int(r['score'] * 100)}%"
                    )
        except Exception as exc:
            logging.warning(f"[Briefing] RAG fehlgeschlagen: {exc}")

    # 3. Prompt zusammenbauen
    parts = [f"Termin: {req.subject}"]
    if req.start:
        parts.append(f"Datum/Uhrzeit: {req.start[:16].replace('T', ' ')}")
    if req.end:
        parts.append(f"Ende: {req.end[:16].replace('T', ' ')}")
    if req.location:
        parts.append(f"Ort: {req.location}")
    if req.body:
        parts.append(f"Terminbeschreibung: {req.body[:300]}")
    if person_name:
        parts.append(f"Erkannte Person: {person_name}")
    if rag_lines:
        parts.append("\nRelevante frühere Mails:")
        parts.extend(rag_lines)
    else:
        parts.append("\nKeine ähnlichen Mails gefunden.")

    user_prompt = "\n".join(parts)

    def generate():
        stream_kwargs = dict(task="chat", prompt=user_prompt, max_tokens=512, system=BRIEFING_SYSTEM)
        try:
            for text in llm.stream(**stream_kwargs):
                yield f"data: {text}\n\n"
        except Exception as exc:
            logging.warning(f"[Briefing] LLM '{getattr(llm, 'mode', '?')}' fehlgeschlagen: {exc}")
            if getattr(llm, "mode", "cloud") != "cloud":
                logging.warning("[Briefing] Fallback auf Cloud-LLM")
                try:
                    for text in get_llm_client("cloud").stream(**stream_kwargs):
                        yield f"data: {text}\n\n"
                except Exception as exc2:
                    logging.warning(f"[Briefing] Cloud-Fallback fehlgeschlagen: {exc2}")
                    yield f"data: [Fehler: LLM nicht erreichbar ({type(exc2).__name__})]\n\n"
            else:
                yield f"data: [Fehler: LLM nicht erreichbar ({type(exc).__name__})]\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


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
    if memory_store.get_fact(fact_id) is None:
        raise HTTPException(status_code=404, detail=f"Fakt nicht gefunden: {fact_id}")
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


# ── Graph / Knowledge-Map ──────────────────────────────────────────────────────
class GraphRequest(BaseModel):
    subject: str
    text: str  # content to analyze (mail body, event description, task body)


@app.post("/api/graph")
def get_graph(req: GraphRequest, session_id: str | None = Cookie(default=None)):
    """Extracts a knowledge graph (nodes + edges) from text using the configured LLM."""
    session = _get_session(session_id)
    llm = _get_llm(session)
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

    try:
        raw = _llm_create(llm, task="graph", prompt=prompt, max_tokens=800).strip()
    except Exception as exc:
        logging.warning(f"[Graph] LLM-Aufruf fehlgeschlagen: {exc}")
        return {
            "nodes": [{"id": "center", "label": req.subject[:30], "type": "center"}],
            "edges": [],
        }
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


# DB HAFAS imports + singleton — must appear before train chat integration helpers
from pyhafas import HafasClient
from pyhafas.profile import NVVProfile
from pyhafas.types.fptf import Station as HafasStation
from datetime import datetime, timedelta, timezone
_tz = timezone  # backwards-compat alias used in train helpers

_hafas = HafasClient(NVVProfile())

# ── Train chat integration ─────────────────────────────────────────────────

_DEFAULT_FROM_NAME = "Nürnberg Hbf"

_TRAIN_EXTRACT_SYSTEM = (
    "Du bist ein Parameterextraktor. Antworte NUR mit einem JSON-Objekt, "
    "kein Text davor oder danach, keine Markdown-Fences. "
    "Extrahiere Abfahrtsort, Zielort und Abfahrtszeit aus der Nachricht. "
    f"Wenn kein Abfahrtsort genannt wird, setze from_name: \"{_DEFAULT_FROM_NAME}\". "
    "Wenn keine Zeit erkennbar ist, setze when: null. "
    "Heutiges Datum: {today}. "
    'Format: {{"from_name": "...", "to_name": "...", "when": "YYYY-MM-DDTHH:MM oder null"}}'
)


def _extract_train_params(message: str, llm) -> dict | None:
    """Kurzer LLM-Call um from_name, to_name, when aus der Nachricht zu extrahieren."""
    import json as _json
    from datetime import date as _date
    today = _date.today().isoformat()
    system = _TRAIN_EXTRACT_SYSTEM.format(today=today)
    try:
        raw = llm.create(task="train_extract", prompt=message, max_tokens=80, system=system)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            raw = raw.strip()
        params = _json.loads(raw)
        if not isinstance(params.get("to_name"), str) or not params["to_name"].strip():
            return None
        if not isinstance(params.get("from_name"), str) or not params["from_name"].strip():
            params["from_name"] = _DEFAULT_FROM_NAME
        return params
    except Exception as exc:
        logging.warning(f"[Train] Parameterextraktion fehlgeschlagen: {exc}")
        return None


def _build_train_nav(message: str, llm) -> str | None:
    """Extrahiert Route, löst Bahnhofsnamen via HAFAS auf, gibt [TRAIN_NAV:{...}] zurück."""
    import json as _json
    params = _extract_train_params(message, llm)
    if not params:
        return None
    try:
        from_stations = _hafas.locations(params["from_name"])
        to_stations = _hafas.locations(params["to_name"])
    except Exception as exc:
        logging.warning(f"[Train] HAFAS locations fehlgeschlagen: {exc}")
        return None
    if not from_stations or not to_stations:
        logging.warning(f"[Train] Bahnhof nicht gefunden: {params}")
        return None
    from_s = from_stations[0]
    to_s = to_stations[0]
    nav = {
        "from_id": from_s.id,
        "from_name": from_s.name,
        "to_id": to_s.id,
        "to_name": to_s.name,
        "when": params.get("when"),
    }
    return f"[TRAIN_NAV:{_json.dumps(nav, ensure_ascii=False)}]"


# ── DB HAFAS Train Planner (via pyHafas + NVV profile) ──────────────────────


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


# ── Ontology Endpoints ────────────────────────────────────────────────────

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
