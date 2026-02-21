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
