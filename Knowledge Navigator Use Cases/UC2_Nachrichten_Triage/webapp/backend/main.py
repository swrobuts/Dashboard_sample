# webapp/backend/main.py
import io
import json
import os
import re
import uuid
from pathlib import Path

import anthropic
import openai
from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

load_dotenv()

app = FastAPI(title="UC2 Nachrichten-Triage", version="1.0.0")


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


from backend.exchange_helpers import connect_to_exchange, fetch_emails

# ── Session-Management (In-Memory) ────────────────────────────────────────
_sessions: dict[str, object] = {}  # session_id → exchangelib Account


class ConnectRequest(BaseModel):
    username: str
    password: str
    institution: str


class FetchRequest(BaseModel):
    max_count: int = 10
    unread_only: bool = True


@app.post("/api/exchange/connect")
def exchange_connect(req: ConnectRequest):
    try:
        account = connect_to_exchange(req.username, req.password, req.institution)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Exchange-Verbindung fehlgeschlagen: {e}")

    session_id = str(uuid.uuid4())
    _sessions[session_id] = account

    resp = JSONResponse(content={
        "status": "connected",
        "inbox_count": account.inbox.total_count,
    })
    resp.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="strict",
        secure=False,  # True im Produktion via Traefik HTTPS
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
    resp = JSONResponse(content={"status": "disconnected"})
    resp.delete_cookie("session_id")
    return resp


# Frontend statisch servieren
_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
