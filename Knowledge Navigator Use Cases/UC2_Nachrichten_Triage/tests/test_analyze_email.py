# tests/test_analyze_email.py
"""
Tests für analyze_email() — Kernfunktion der Nachrichten-Triage.
Wichtig: Kein echter API-Call! Wir mocken den Claude-Client.
Das zeigt, wie man LLM-Funktionen sauber testbar macht.
"""
import json
import pytest

# ── CO-STAR Prompt Template ──────────────────────────────────────────────────
# C=Context, O=Objective, S=Style, T=Tone, A=Audience, R=Response
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
- VIP: Vorgesetzte, Dekanat, wichtige Partner → sofortige Reaktion
- Aktion nötig: Studierende, Kollegen mit Anfragen → Antwort diese Woche
- Nur Info: Newsletter, FYI-Mails → lesen wenn Zeit da
- Ignorieren: Spam, Werbung, irrelevant → löschen

E-Mail:
{email_text}
"""
# ── Ende CO-STAR Template ────────────────────────────────────────────────────


def analyze_email(email_text: str, client) -> dict:
    """
    Analysiert eine E-Mail und gibt eine strukturierte Triage zurück.

    Args:
        email_text: Der vollständige E-Mail-Text (Betreff + Body)
        client: Anthropic-Client (echter Client oder Mock für Tests)

    Returns:
        dict mit: kategorie, priorität, zusammenfassung, empfohlene_aktion
    """
    prompt = COSTAR_PROMPT.format(email_text=email_text)

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    return json.loads(raw)


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
