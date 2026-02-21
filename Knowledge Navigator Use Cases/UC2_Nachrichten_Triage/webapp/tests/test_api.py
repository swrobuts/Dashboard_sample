# webapp/tests/test_api.py
from fastapi.testclient import TestClient


def get_client():
    from backend.main import app
    return TestClient(app)


def test_health_returns_ok():
    client = get_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
