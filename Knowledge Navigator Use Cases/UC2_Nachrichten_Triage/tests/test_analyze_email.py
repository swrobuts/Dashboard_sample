# tests/test_analyze_email.py
"""
Tests für analyze_email() — Kernfunktion der Nachrichten-Triage.
Wichtig: Kein echter API-Call! Wir mocken den Claude-Client.
Das zeigt, wie man LLM-Funktionen sauber testbar macht.
"""
import json
import pytest


def analyze_email(email_text: str, client) -> dict:
    """Zu implementierende Funktion — wird in Task 4 gebaut."""
    pass  # noch nicht implementiert


def test_analyze_email_returns_dict(mocker):
    """analyze_email gibt ein dict zurück."""
    mock_response = mocker.MagicMock()
    mock_response.content[0].text = json.dumps({
        "kategorie": "VIP",
        "priorität": 1,
        "zusammenfassung": "Dekan fordert Stellungnahme bis 18 Uhr.",
        "empfohlene_aktion": "Sofort antworten."
    })
    mock_client = mocker.MagicMock()
    mock_client.messages.create.return_value = mock_response
    result = analyze_email("Test-E-Mail", mock_client)
    assert isinstance(result, dict)


def test_analyze_email_has_required_fields(mocker):
    """Das Ergebnis enthält alle vier Pflichtfelder."""
    mock_response = mocker.MagicMock()
    mock_response.content[0].text = json.dumps({
        "kategorie": "VIP",
        "priorität": 1,
        "zusammenfassung": "Dekan fordert Stellungnahme.",
        "empfohlene_aktion": "Sofort antworten."
    })
    mock_client = mocker.MagicMock()
    mock_client.messages.create.return_value = mock_response
    result = analyze_email("Test-E-Mail", mock_client)
    assert "kategorie" in result
    assert "priorität" in result
    assert "zusammenfassung" in result
    assert "empfohlene_aktion" in result


def test_analyze_email_kategorie_valid(mocker):
    """Kategorie ist einer der vier erlaubten Werte."""
    VALID_CATEGORIES = {"VIP", "Aktion nötig", "Nur Info", "Ignorieren"}
    mock_response = mocker.MagicMock()
    mock_response.content[0].text = json.dumps({
        "kategorie": "Aktion nötig",
        "priorität": 2,
        "zusammenfassung": "Student fragt wegen Abgabe.",
        "empfohlene_aktion": "Bis Freitag antworten."
    })
    mock_client = mocker.MagicMock()
    mock_client.messages.create.return_value = mock_response
    result = analyze_email("Test-E-Mail", mock_client)
    assert result["kategorie"] in VALID_CATEGORIES


def test_analyze_email_priorität_range(mocker):
    """Priorität ist eine Zahl zwischen 1 und 4."""
    mock_response = mocker.MagicMock()
    mock_response.content[0].text = json.dumps({
        "kategorie": "Nur Info",
        "priorität": 3,
        "zusammenfassung": "Springer Newsletter.",
        "empfohlene_aktion": "Kein Handlungsbedarf."
    })
    mock_client = mocker.MagicMock()
    mock_client.messages.create.return_value = mock_response
    result = analyze_email("Test-E-Mail", mock_client)
    assert 1 <= result["priorität"] <= 4
