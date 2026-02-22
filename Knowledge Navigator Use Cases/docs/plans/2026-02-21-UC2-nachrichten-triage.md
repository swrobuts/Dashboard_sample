# UC2: Nachrichten-Triage — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Jupyter Notebook, in das man eine E-Mail einfügt und das via Claude API eine strukturierte Triage ausgibt (Kategorie, Priorität, Zusammenfassung, Empfehlung).

**Architecture:** Einzel-Notebook mit zwei Ebenen — Kernfunktion (`analyze_email`) + interaktives UI via `ipywidgets`. Die Kernfunktion ist separat mit pytest testbar (via Mock-Client). Deployment auf Deepnote. API-Key kommt aus Umgebungsvariable, niemals aus dem Code.

**Tech Stack:** Python 3.11+, `anthropic`, `python-dotenv`, `ipywidgets`, `pytest`, `pytest-mock`

**Original KN-Szene (1987):** Phil spielt drei Nachrichten ab und gibt dem Professor einen priorisierten Überblick — Forschungsteam, Student, Mutter. Heute: KI liest 20 Mails und sortiert in Sekunden.

**CO-STAR + Chain-of-Thought:** Alle LLM-Aufrufe folgen dem CO-STAR-Framework. Im Code dokumentiert.

---

## Dateistruktur (Ziel)

```
UC2_Nachrichten_Triage/
├── nachrichten_triage.ipynb   ← Haupt-Notebook (Deepnote)
├── requirements.txt            ← Abhängigkeiten
├── .env.example               ← Template (KEIN echter Key!)
├── tests/
│   └── test_analyze_email.py  ← pytest-Tests (Mock)
└── sample_emails/
    ├── email_01_vip.txt
    ├── email_02_aktion.txt
    ├── email_03_info.txt
    └── email_04_ignorieren.txt
```

---

## Task 1: Projektstruktur anlegen

**Files:**
- Create: `UC2_Nachrichten_Triage/requirements.txt`
- Create: `UC2_Nachrichten_Triage/.env.example`
- Create: `UC2_Nachrichten_Triage/tests/__init__.py`

**Step 1: requirements.txt anlegen**

Inhalt:
```
anthropic>=0.40.0
python-dotenv>=1.0.0
ipywidgets>=8.0.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

**Step 2: .env.example anlegen**

Inhalt:
```
# API-Key von https://console.anthropic.com
# NIEMALS den echten Key in Git committen!
# Lokale Datei: .env (in .gitignore eingetragen)
# Deepnote: Environment Variables im Projekt-Panel setzen

ANTHROPIC_API_KEY=sk-ant-DEIN-KEY-HIER
```

**Step 3: .gitignore prüfen / anlegen**

Inhalt (Datei im Projektroot, falls noch nicht vorhanden):
```
.env
__pycache__/
.ipynb_checkpoints/
*.pyc
```

**Step 4: Verzeichnisse anlegen**
```bash
cd "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage"
mkdir -p tests sample_emails
touch tests/__init__.py
```

**Step 5: Commit**
```bash
git add UC2_Nachrichten_Triage/
git commit -m "feat(UC2): project scaffold - requirements, env template, gitignore"
```

---

## Task 2: Sample-E-Mails erstellen

**Files:**
- Create: `UC2_Nachrichten_Triage/sample_emails/email_01_vip.txt`
- Create: `UC2_Nachrichten_Triage/sample_emails/email_02_aktion.txt`
- Create: `UC2_Nachrichten_Triage/sample_emails/email_03_info.txt`
- Create: `UC2_Nachrichten_Triage/sample_emails/email_04_ignorieren.txt`

**Step 1: email_01_vip.txt** (Dekan — sofortiger Handlungsbedarf)
```
Von: dekan@thws.de
An: robert.butscher@thws.de
Betreff: DRINGEND: Prüfungsausschuss morgen 9:00 Uhr — Stellungnahme erforderlich

Lieber Herr Butscher,

der Prüfungsausschuss tritt morgen um 9:00 Uhr zusammen. Ein Student hat
Einspruch gegen seine Bewertung in Ihrem Kurs eingereicht. Bitte senden Sie
mir bis heute Abend 18:00 Uhr Ihre schriftliche Stellungnahme.

Mit freundlichen Grüßen
Prof. Dr. Weber
Dekan Fakultät Wirtschaft
```

**Step 2: email_02_aktion.txt** (Student — Antwort nötig, aber nicht dringend)
```
Von: max.mustermann@student.thws.de
An: robert.butscher@thws.de
Betreff: Frage zur Abgabe Fallstudie KI

Hallo Herr Prof. Butscher,

ich wollte fragen, ob wir die Fallstudie auch als Einzelarbeit einreichen
können, da meine Gruppe sich leider aufgelöst hat.

Können Sie mir bitte bis Ende der Woche Bescheid geben?

Viele Grüße
Max Mustermann, Matrikelnummer 12345678
```

**Step 3: email_03_info.txt** (Newsletter — keine Aktion)
```
Von: newsletter@springer.com
An: robert.butscher@thws.de
Betreff: Neue Publikationen im Bereich KI & Maschinelles Lernen — Februar 2026

Sehr geehrter Herr Prof. Dr. Butscher,

wir freuen uns, Ihnen die neuesten Publikationen aus unserem Verlag vorzustellen:

- "Generative AI in Education" (Müller et al., 2026)
- "Responsible AI Frameworks" (Schmidt, 2026)
[... weitere 12 Titel ...]

Ihr Springer-Team
```

**Step 4: email_04_ignorieren.txt** (Spam)
```
Von: noreply@gewinnspiel-super.de
An: robert.butscher@thws.de
Betreff: Sie haben gewonnen!!! 🎉🎉🎉

Herzlichen Glückwunsch!!!

Sie wurden als Gewinner unseres exklusiven Gewinnspiels ausgewählt!!!
Klicken Sie JETZT auf den Link um Ihren Preis zu beanspruchen!!!

[JETZT GEWINNEN!!!]
```

**Step 5: Commit**
```bash
git add UC2_Nachrichten_Triage/sample_emails/
git commit -m "feat(UC2): add 4 sample emails covering all triage categories"
```

---

## Task 3: Kernfunktion mit Test (TDD)

**Files:**
- Create: `UC2_Nachrichten_Triage/tests/test_analyze_email.py`

**Step 1: Failing Test schreiben**

```python
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
    # Mock: Simuliert Claude-Antwort ohne echten API-Call
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
```

**Step 2: Tests laufen lassen — müssen FAIL sein**
```bash
cd "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage"
pytest tests/test_analyze_email.py -v
```
Erwartet: `FAILED` — `analyze_email` gibt `None` zurück (noch nicht implementiert).

**Step 3: Commit (failing tests)**
```bash
git add tests/test_analyze_email.py
git commit -m "test(UC2): add failing tests for analyze_email (TDD)"
```

---

## Task 4: Kernfunktion implementieren

**Files:**
- Modify: `UC2_Nachrichten_Triage/tests/test_analyze_email.py` (analyze_email ersetzen)

> Hinweis: In einem Notebook-Projekt definieren wir `analyze_email` direkt im Test-File
> für Task 3+4. Im Notebook selbst wird sie in einer eigenen Zelle definiert.

**Step 1: analyze_email implementieren** — ersetze die `pass`-Funktion:

```python
# Am Anfang der test_analyze_email.py, nach den imports:
import json
import pytest

# ── CO-STAR Prompt Template ──────────────────────────────────────────────────
# Dieses Template folgt dem CO-STAR-Framework:
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
    # Chain-of-Thought: Claude soll explizit kategorisieren
    prompt = COSTAR_PROMPT.format(email_text=email_text)

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    return json.loads(raw)
```

**Step 2: Tests laufen lassen — müssen PASS sein**
```bash
pytest tests/test_analyze_email.py -v
```
Erwartet:
```
PASSED tests/test_analyze_email.py::test_analyze_email_returns_dict
PASSED tests/test_analyze_email.py::test_analyze_email_has_required_fields
PASSED tests/test_analyze_email.py::test_analyze_email_kategorie_valid
PASSED tests/test_analyze_email.py::test_analyze_email_priorität_range
4 passed in 0.XXs
```

**Step 3: Commit**
```bash
git add tests/test_analyze_email.py
git commit -m "feat(UC2): implement analyze_email with CO-STAR prompt — all tests green"
```

---

## Task 5: Jupyter Notebook bauen

**Files:**
- Create: `UC2_Nachrichten_Triage/nachrichten_triage.ipynb`

Das Notebook hat 8 Zellen. Jede Zelle wird einzeln angelegt.

---

**Step 1: Zelle 1 — Titel & Kontext (Markdown)**

````markdown
# 📬 UC2: Nachrichten-Triage
### Knowledge Navigator 1987 → 2026

**Originalszene:** Phil spielt dem Professor drei Nachrichten vor und gibt einen
priorisierten Überblick — Forschungsteam aus Guatemala, Student Jordan, seine Mutter.

**Heute:** Statt einer Sprachnachricht analysiert eine KI automatisch deine E-Mails
und sortiert sie in Sekunden nach Priorität und Handlungsbedarf.

---
**Lernziele:**
- Claude API aufrufen
- CO-STAR Prompt-Framework anwenden
- Strukturierten JSON-Output verarbeiten
- ipywidgets für interaktive Notebooks nutzen

**Tech Stack:** Python · Anthropic Claude API · ipywidgets · python-dotenv
````

---

**Step 2: Zelle 2 — Setup (Code)**

```python
# ── Setup: Bibliotheken laden & API-Key ─────────────────────────────────────
# Für lokale Entwicklung: API-Key aus .env Datei
# Für Deepnote: Environment Variable im Projekt-Panel setzen
# REGEL: Niemals den API-Key direkt in den Code schreiben!

import json
import os
from pathlib import Path

import anthropic
import ipywidgets as widgets
from dotenv import load_dotenv
from IPython.display import display, HTML

# .env laden (lokal) — auf Deepnote wird die Umgebungsvariable direkt genutzt
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError(
        "ANTHROPIC_API_KEY nicht gefunden!\n"
        "Lokal: .env Datei anlegen (siehe .env.example)\n"
        "Deepnote: Environment Variables im Projekt-Panel setzen"
    )

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
print("✅ Claude-Client initialisiert")
```

---

**Step 3: Zelle 3 — CO-STAR Prompt (Code, dokumentiert)**

```python
# ── CO-STAR Prompt Template ──────────────────────────────────────────────────
#
# Das CO-STAR-Framework strukturiert LLM-Prompts in 6 Dimensionen:
#
#   C — Context:    Wer ist der Assistent? In welchem Kontext arbeitet er?
#   O — Objective:  Was soll konkret erreicht werden?
#   S — Style:      Wie soll die Antwort formuliert sein?
#   T — Tone:       Welcher Ton ist angemessen?
#   A — Audience:   Für wen ist die Ausgabe bestimmt?
#   R — Response:   Welches Format soll die Antwort haben?
#
# Zusätzlich: Chain-of-Thought — die Kategorien sind explizit definiert,
# damit Claude nachvollziehbar klassifiziert.
# ─────────────────────────────────────────────────────────────────────────────

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
- VIP          (Priorität 1): Dekanat, Vorgesetzte, wichtige Partner
- Aktion nötig (Priorität 2): Studierende, Kollegen mit konkreten Anfragen
- Nur Info     (Priorität 3): Newsletter, FYI-Mails, Informationen ohne Handlungsbedarf
- Ignorieren   (Priorität 4): Spam, Werbung, irrelevant

E-Mail:
{email_text}
"""

print("✅ CO-STAR Prompt Template geladen")
```

---

**Step 4: Zelle 4 — Kernfunktion (Code)**

```python
# ── Kernfunktion: analyze_email ──────────────────────────────────────────────

def analyze_email(email_text: str) -> dict:
    """
    Analysiert eine E-Mail per Claude API und gibt eine strukturierte Triage zurück.

    Args:
        email_text: Vollständiger E-Mail-Text (Betreff + Absender + Body)

    Returns:
        dict: {kategorie, priorität, zusammenfassung, empfohlene_aktion}
    """
    prompt = COSTAR_PROMPT.format(email_text=email_text)

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    return json.loads(raw)


def format_result_html(result: dict, email_preview: str) -> str:
    """Formatiert das Triage-Ergebnis als farbiges HTML."""
    farben = {
        "VIP":          ("#dc2626", "🔴"),
        "Aktion nötig": ("#d97706", "🟡"),
        "Nur Info":     ("#2563eb", "🔵"),
        "Ignorieren":   ("#6b7280", "⚫"),
    }
    farbe, emoji = farben.get(result["kategorie"], ("#6b7280", "⚫"))

    return f"""
    <div style="border-left: 4px solid {farbe}; padding: 12px 16px;
                margin: 8px 0; background: #f9fafb; border-radius: 4px;">
        <div style="font-size: 18px; font-weight: bold; color: {farbe};">
            {emoji} {result['kategorie']} &nbsp;
            <span style="font-size:13px; color:#6b7280;">
                Priorität {result['priorität']}/4
            </span>
        </div>
        <div style="margin-top: 8px; color: #374151;">
            <b>Zusammenfassung:</b> {result['zusammenfassung']}
        </div>
        <div style="margin-top: 4px; color: #374151;">
            <b>Empfehlung:</b> {result['empfohlene_aktion']}
        </div>
        <div style="margin-top: 8px; font-size: 11px; color: #9ca3af;">
            E-Mail-Vorschau: {email_preview[:80]}...
        </div>
    </div>
    """

print("✅ Funktionen definiert")
```

---

**Step 5: Zelle 5 — Interaktives UI (Code)**

```python
# ── Interaktives UI mit ipywidgets ───────────────────────────────────────────

email_input = widgets.Textarea(
    placeholder="E-Mail hier einfügen (Von: / Betreff: / Text) ...",
    layout=widgets.Layout(width="100%", height="200px")
)

analyse_btn = widgets.Button(
    description="📬 Analysieren",
    button_style="primary",
    layout=widgets.Layout(width="160px", height="40px")
)

output = widgets.Output()

def on_analyse_click(b):
    with output:
        output.clear_output()
        email_text = email_input.value.strip()
        if not email_text:
            display(HTML("<p style='color:red'>⚠️ Bitte E-Mail-Text einfügen.</p>"))
            return
        display(HTML("<p>⏳ Analysiere...</p>"))
        try:
            result = analyze_email(email_text)
            output.clear_output()
            display(HTML(format_result_html(result, email_text)))
            # Rohes JSON für Lernzwecke anzeigen
            print("\n📄 Rohes JSON (für Entwickler):")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except json.JSONDecodeError as e:
            display(HTML(f"<p style='color:red'>❌ JSON-Fehler: {e}</p>"))
        except Exception as e:
            display(HTML(f"<p style='color:red'>❌ Fehler: {e}</p>"))

analyse_btn.on_click(on_analyse_click)

display(
    widgets.HTML("<h3>📬 E-Mail einfügen und analysieren</h3>"),
    email_input,
    analyse_btn,
    output
)
```

---

**Step 6: Zelle 6 — Demo mit Sample-E-Mails (Code)**

```python
# ── Demo: Alle 4 Sample-E-Mails auf einmal analysieren ───────────────────────

sample_dir = Path("sample_emails")
sample_files = sorted(sample_dir.glob("*.txt"))

print(f"🔍 Analysiere {len(sample_files)} Sample-E-Mails...\n")

results_html = "<h3>📊 Triage-Ergebnisse</h3>"
for f in sample_files:
    email_text = f.read_text(encoding="utf-8")
    result = analyze_email(email_text)
    results_html += format_result_html(result, email_text)

display(HTML(results_html))
```

---

**Step 7: Zelle 7 — Erweiterungsideen (Markdown)**

````markdown
## 🚀 Erweiterungen (Stufe 2)

### exchangelib-Anbindung (UC2 Stufe 2)
Statt E-Mails manuell einzufügen, verbindet sich das Notebook mit deinem
Exchange-Postfach (THWS oder DHBW) und analysiert automatisch alle ungelesenen Mails.

```python
from exchangelib import Credentials, Account

credentials = Credentials(username="vorname.nachname@thws.de", password="***")
account = Account("vorname.nachname@thws.de", credentials=credentials, autodiscover=True)

for mail in account.inbox.filter(is_read=False).order_by("-datetime_received")[:20]:
    result = analyze_email(f"Von: {mail.sender}\nBetreff: {mail.subject}\n\n{mail.text_body}")
    print(result)
```

### Batch-Analyse + Export
Ergebnisse als CSV oder HTML-Report exportieren.

### Feedback-Loop
Benutzer korrigiert die Kategorie → wird für Fine-Tuning oder Few-Shot-Prompts gespeichert.
````

---

**Step 8: Notebook-Datei committen**
```bash
git add UC2_Nachrichten_Triage/nachrichten_triage.ipynb
git commit -m "feat(UC2): complete notebook - CO-STAR triage, ipywidgets UI, demo cells"
```

---

## Task 6: Deepnote-Deployment vorbereiten

**Files:**
- Create: `UC2_Nachrichten_Triage/README.md`

**Step 1: README.md anlegen**

```markdown
# UC2: Nachrichten-Triage

**Knowledge Navigator 1987 → 2026**
Original-Szene: Phil spielt drei priorisierte Nachrichten ab.
Heute: KI analysiert und sortiert E-Mails in Sekunden.

## Quickstart (lokal)

```bash
pip install -r requirements.txt
cp .env.example .env
# .env bearbeiten: ANTHROPIC_API_KEY eintragen
jupyter lab nachrichten_triage.ipynb
```

## Deepnote

1. Notebook in Deepnote importieren (Upload oder GitHub-Sync)
2. Environment Variables → `ANTHROPIC_API_KEY` setzen
3. `requirements.txt` wird automatisch erkannt
4. Zellen von oben nach unten ausführen

## Sicherheit

⚠️ API-Keys **niemals** in Notebook-Zellen schreiben.
Immer über Umgebungsvariablen (`.env` lokal, Deepnote Secrets im Deployment).

## Tech Stack

| Tool | Zweck |
|------|-------|
| `anthropic` | Claude API Client |
| `ipywidgets` | Interaktives UI im Notebook |
| `python-dotenv` | Lokale Umgebungsvariablen |
| `pytest` + `pytest-mock` | Tests ohne echten API-Call |

## CO-STAR Prompt

Siehe Zelle 3 im Notebook — vollständig kommentiert.
```

**Step 2: Alles committen**
```bash
git add UC2_Nachrichten_Triage/README.md
git commit -m "docs(UC2): add README with quickstart, Deepnote instructions, security notes"
```

---

## Task 7: Finaler Check

**Step 1: Alle Tests grün?**
```bash
pytest UC2_Nachrichten_Triage/tests/ -v
```
Erwartet: 4 passed.

**Step 2: Notebook vollständig durchlaufen?**
In DataSpell oder Jupyter: Kernel → Restart & Run All.
Alle Zellen müssen ohne Fehler durchlaufen.

**Step 3: Final Commit**
```bash
git add -A
git commit -m "feat(UC2): Nachrichten-Triage Stufe 1 complete — ready for Deepnote"
```

---

## Zusammenfassung

| Task | Inhalt | Status |
|------|--------|--------|
| 1 | Projektstruktur + .env.example + .gitignore | ⬜ |
| 2 | 4 Sample-E-Mails (VIP, Aktion, Info, Spam) | ⬜ |
| 3 | Failing Tests (TDD) | ⬜ |
| 4 | analyze_email() implementiert — Tests grün | ⬜ |
| 5 | Notebook: 7 Zellen (Intro, Setup, Prompt, Funktion, UI, Demo, Erweiterung) | ⬜ |
| 6 | README + Deepnote-Deployment | ⬜ |
| 7 | Finaler Check | ⬜ |

**Nächster Schritt nach UC2 Stufe 1:** UC2 Stufe 2 (exchangelib-Anbindung) oder UC1 (Phil Tagesüberblick).
