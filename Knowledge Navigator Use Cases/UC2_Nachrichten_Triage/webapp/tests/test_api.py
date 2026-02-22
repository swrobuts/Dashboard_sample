# webapp/tests/test_api.py
import json
import pytest
from fastapi.testclient import TestClient


def get_client():
    from backend.main import app
    return TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────

def _login(client, mocker, inbox_count=5):
    """Helper: Mock IMAP (THWS), do auth/login, return (response, imap_config_dict)."""
    mock_config = {
        "host": "webmail.thws.de",
        "port": 993,
        "username": "robert.butscher",
        "password": "geheim",
        "inbox_count": inbox_count,
    }
    mocker.patch("backend.main.connect_to_imap", return_value=mock_config)
    r = client.post("/api/auth/login", json={
        "username": "robert.butscher",
        "password": "geheim",
        "institution": "THWS",
    })
    return r, mock_config


def _login_ews(client, mocker, inbox_count=5):
    """Helper: Mock EWS (DHBW), do auth/login, return (response, mock_account)."""
    mock_account = mocker.MagicMock()
    mock_account.inbox.total_count = inbox_count
    mock_account.inbox.unread_count = 0
    mock_account.drafts.total_count = 0
    # sent.filter(...).only(...) must return an iterable of zero items (for sent_today count)
    mock_account.sent.filter.return_value.only.return_value = iter([])
    mocker.patch("backend.main.connect_to_exchange", return_value=mock_account)
    r = client.post("/api/auth/login", json={
        "username": "max.mustermann@dhbw-test.de",
        "password": "geheim",
        "institution": "DHBW",
    })
    return r, mock_account


def _clear_lockout():
    """Reset global lockout state between tests."""
    import backend.main as m
    m._lockout.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Existing Tests (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def test_health_returns_ok():
    client = get_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
    r = client.post("/api/exchange/connect", json={
        "username": "u", "password": "p", "institution": "THWS",
    })
    session_id = r.cookies["session_id"]

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


# ═══════════════════════════════════════════════════════════════════════════
# New Tests: Auth
# ═══════════════════════════════════════════════════════════════════════════

def test_auth_login_success(mocker):
    """POST /api/auth/login → 200 + session_id cookie + username."""
    _clear_lockout()
    client = get_client()
    r, _ = _login(client, mocker, inbox_count=7)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["username"] == "robert.butscher"
    assert data["inbox_count"] == 7
    assert "session_id" in r.cookies


def test_auth_login_wrong_credentials(mocker):
    """POST /api/auth/login mit falschen Credentials → 401."""
    _clear_lockout()
    import imaplib
    mocker.patch("backend.main.connect_to_imap",
                 side_effect=imaplib.IMAP4.error(b"LOGIN failed."))
    client = get_client()
    r = client.post("/api/auth/login", json={
        "username": "wrong", "password": "nope", "institution": "THWS",
    })
    assert r.status_code == 401


def test_auth_login_lockout(mocker):
    """3 Fehlversuche → 4. Versuch gibt 429 zurück."""
    _clear_lockout()
    import imaplib
    mocker.patch("backend.main.connect_to_imap",
                 side_effect=imaplib.IMAP4.error(b"LOGIN failed."))
    client = get_client()
    payload = {"username": "u", "password": "x", "institution": "THWS"}

    # 3 Fehlversuche — alle 401
    for _ in range(3):
        r = client.post("/api/auth/login", json=payload)
        assert r.status_code == 401

    # 4. Versuch → gesperrt
    r = client.post("/api/auth/login", json=payload)
    assert r.status_code == 429
    data = r.json()
    assert "retry_after" in data.get("detail", data)

    _clear_lockout()  # cleanup


def test_auth_logout(mocker):
    """POST /api/auth/logout → 200 + session gelöscht."""
    _clear_lockout()
    client = get_client()
    r, _ = _login(client, mocker)
    assert r.status_code == 200
    session_id = r.cookies["session_id"]

    r2 = client.post("/api/auth/logout", cookies={"session_id": session_id})
    assert r2.status_code == 200
    assert r2.json()["status"] == "logged_out"

    # Session ungültig nach Logout
    r3 = client.get("/api/auth/me", cookies={"session_id": session_id})
    assert r3.status_code == 401


def test_auth_me_with_session(mocker):
    """GET /api/auth/me mit gültiger Session → 200 + username."""
    _clear_lockout()
    client = get_client()
    r, _ = _login(client, mocker)
    session_id = r.cookies["session_id"]

    r2 = client.get("/api/auth/me", cookies={"session_id": session_id})
    assert r2.status_code == 200
    data = r2.json()
    assert data["username"] == "robert.butscher"
    assert data["institution"] == "THWS"
    assert "ews_connected" in data


def test_auth_me_without_session():
    """GET /api/auth/me ohne Session → 401."""
    client = get_client()
    r = client.get("/api/auth/me")
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# New Tests: Calendar & Tasks (session protection)
# ═══════════════════════════════════════════════════════════════════════════

def test_calendar_requires_session():
    """GET /api/calendar ohne Session → 401."""
    client = get_client()
    r = client.get("/api/calendar", cookies={"session_id": "invalid"})
    assert r.status_code == 401


def test_tasks_requires_session():
    """GET /api/tasks ohne Session → 401."""
    client = get_client()
    r = client.get("/api/tasks", cookies={"session_id": "invalid"})
    assert r.status_code == 401


def test_tasks_create(mocker):
    """POST /api/tasks/create mit EWS-Session (DHBW) → 200."""
    _clear_lockout()
    client = get_client()
    r, mock_account = _login_ews(client, mocker)
    session_id = r.cookies["session_id"]

    # Mock create_task
    mocker.patch("backend.main.create_task",
                 return_value={"id": "task-123", "subject": "Klausur vorbereiten"})

    r2 = client.post("/api/tasks/create",
                     json={"subject": "Klausur vorbereiten", "priority": "High"},
                     cookies={"session_id": session_id})
    assert r2.status_code == 200
    assert r2.json()["subject"] == "Klausur vorbereiten"


def test_calendar_create(mocker):
    """POST /api/calendar/create (Google Calendar) mit gültiger Session → 200."""
    _clear_lockout()
    client = get_client()
    r, mock_account = _login_ews(client, mocker)
    session_id = r.cookies["session_id"]

    # Mock create_google_calendar_event (calendar no longer uses EWS)
    mocker.patch("backend.main.create_google_calendar_event",
                 return_value={"id": "cal-456", "subject": "Vorlesung BWL"})

    r2 = client.post("/api/calendar/create",
                     json={
                         "subject": "Vorlesung BWL",
                         "start": "2026-03-01T09:00:00",
                         "end": "2026-03-01T11:00:00",
                     },
                     cookies={"session_id": session_id})
    assert r2.status_code == 200
    assert r2.json()["subject"] == "Vorlesung BWL"


# ═══════════════════════════════════════════════════════════════════════════
# New Tests: Chat
# ═══════════════════════════════════════════════════════════════════════════

def test_chat_requires_session():
    """POST /api/chat ohne Session → 401."""
    client = get_client()
    r = client.post("/api/chat",
                    json={"message": "Was steht heute an?"},
                    cookies={"session_id": "invalid"})
    assert r.status_code == 401


def test_chat_returns_stream(mocker):
    """POST /api/chat mit Session → 200 text/event-stream."""
    _clear_lockout()
    client = get_client()
    r, mock_account = _login(client, mocker)
    session_id = r.cookies["session_id"]

    # THWS-Session is IMAP → fetch_emails_imap is used; calendar/tasks return []
    mocker.patch("backend.main.fetch_emails_imap", return_value=[])

    # Mock Anthropic streaming
    mock_stream_ctx = mocker.MagicMock()
    mock_stream_ctx.__enter__ = mocker.MagicMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__exit__ = mocker.MagicMock(return_value=False)
    mock_stream_ctx.text_stream = iter(["Guten ", "Morgen!"])
    mocker.patch("backend.main.anthropic_client.messages.stream",
                 return_value=mock_stream_ctx)

    r2 = client.post("/api/chat",
                     json={"message": "Was steht heute an?", "include_context": False},
                     cookies={"session_id": session_id})
    assert r2.status_code == 200
    assert "text/event-stream" in r2.headers["content-type"]
    body = r2.text
    assert "data: " in body


# ═══════════════════════════════════════════════════════════════════════════
# New Tests: RAG — Auto-index after triage
# ═══════════════════════════════════════════════════════════════════════════

def test_analyze_indexes_mail_when_mail_id_provided(mocker):
    """After successful triage, the mail is indexed in the knowledge store."""
    mock_index = mocker.patch("backend.main.knowledge_store.index_mail")
    mocker.patch("backend.main.anthropic_client.messages.create",
        return_value=mocker.Mock(
            content=[mocker.Mock(text='{"kategorie":"VIP","priorität":1,"zusammenfassung":"Test","empfohlene_aktion":"Antworten","stimmung":0.5}')]
        )
    )
    client = get_client()
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
    mock_index = mocker.patch("backend.main.knowledge_store.index_mail")
    mocker.patch("backend.main.anthropic_client.messages.create",
        return_value=mocker.Mock(
            content=[mocker.Mock(text='{"kategorie":"Nur Info","priorität":3,"zusammenfassung":"ok","empfohlene_aktion":"Ignorieren","stimmung":0.0}')]
        )
    )
    client = get_client()
    response = client.post("/api/analyze", json={"email_text": "test"})
    assert response.status_code == 200
    mock_index.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# New Tests: RAG — GET /api/knowledge/search
# ═══════════════════════════════════════════════════════════════════════════

def test_knowledge_search_requires_session():
    client = get_client()
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
    client = get_client()
    response = client.get("/api/knowledge/search?q=Projektverzögerung")
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["subject"] == "Projektstatus"
    assert data["results"][0]["score"] == 0.92


def test_chat_includes_rag_context(mocker):
    """Knowledge base results appear in the prompt sent to Claude."""
    mocker.patch("backend.main._get_session", return_value={"username": "test"})
    mocker.patch("backend.main.fetch_emails", return_value=[])
    mocker.patch("backend.main.fetch_tasks", return_value=[])
    mocker.patch("backend.main.fetch_google_calendar", return_value=[])
    mocker.patch("backend.main.knowledge_store.search", return_value=[
        {"id": "m1", "subject": "Förderantrag 2025", "sender": "dfg@example.de",
         "date": "2025-11-01", "kategorie": "VIP",
         "summary": "DFG-Förderung genehmigt.", "score": 0.88},
    ])
    captured = {}
    def fake_stream(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.MagicMock(return_value=mocker.MagicMock(text_stream=iter(["ok"])))
        mock_ctx.__exit__ = mocker.MagicMock(return_value=False)
        return mock_ctx
    mocker.patch("backend.main.anthropic_client.messages.stream", side_effect=fake_stream)

    client_inst = get_client()
    client_inst.post("/api/chat", json={"message": "Was war mit dem Förderantrag?", "include_context": True})

    assert "messages" in captured, "fake_stream was never called"
    user_content = captured["messages"][0]["content"]
    assert "MAILHISTORIE" in user_content
    assert "Förderantrag 2025" in user_content
