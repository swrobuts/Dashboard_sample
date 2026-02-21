# UC2: Nachrichten-Triage

**Knowledge Navigator 1987 → 2026**

> Originalszene: Phil spielt drei priorisierte Nachrichten ab (Forschungsteam, Student, Mutter).
> Heute: KI analysiert und sortiert E-Mails in Sekunden nach Kategorie und Handlungsbedarf.

## Quickstart (lokal)

```bash
# 1. Abhängigkeiten installieren
pip install -r requirements.txt

# 2. API-Key einrichten
cp .env.example .env
# .env öffnen und ANTHROPIC_API_KEY eintragen

# 3. Notebook starten
jupyter lab nachrichten_triage.ipynb
```

## Deepnote

1. Notebook in Deepnote importieren (Upload oder GitHub-Sync)
2. Im Deepnote Projekt-Panel: **Environment Variables** → `ANTHROPIC_API_KEY` setzen
3. `requirements.txt` wird automatisch erkannt und installiert
4. Zellen von oben nach unten ausführen (Run All)

## Sicherheit

⚠️ **API-Keys niemals in Notebook-Zellen schreiben!**
- Lokal: `.env` Datei (steht in `.gitignore`, wird nicht committed)
- Deepnote: Environment Variables (verschlüsselt gespeichert)
- Git: Nur `.env.example` mit Platzhalter committen

## Projektstruktur

```
UC2_Nachrichten_Triage/
├── nachrichten_triage.ipynb   # Haupt-Notebook
├── requirements.txt            # Abhängigkeiten
├── .env.example               # API-Key Template (kein echter Key!)
├── .gitignore                  # Schützt .env vor Git
├── tests/
│   └── test_analyze_email.py  # pytest-Tests (Mock, kein API-Call nötig)
└── sample_emails/
    ├── email_01_vip.txt        # Kategorie: VIP
    ├── email_02_aktion.txt     # Kategorie: Aktion nötig
    ├── email_03_info.txt       # Kategorie: Nur Info
    └── email_04_ignorieren.txt # Kategorie: Ignorieren
```

## Tech Stack

| Tool | Version | Zweck |
|------|---------|-------|
| `anthropic` | ≥0.40 | Claude API Client |
| `ipywidgets` | ≥8.0 | Interaktives UI im Notebook |
| `python-dotenv` | ≥1.0 | Lokale Umgebungsvariablen |
| `pytest` | ≥8.0 | Test-Framework |
| `pytest-mock` | ≥3.12 | Mock-Client für Tests ohne API-Call |

## CO-STAR Prompt

Das CO-STAR-Framework strukturiert den LLM-Prompt in 6 Dimensionen:

| Dimension | Inhalt |
|-----------|--------|
| **C** ontext | Intelligenter E-Mail-Assistent für Hochschuldozenten |
| **O** bjective | E-Mail kategorisieren, priorisieren, zusammenfassen |
| **S** tyle | Strukturiert, präzise, ohne Füllwörter |
| **T** one | Professionell und sachlich |
| **A** udience | Dozent will in 5 Sekunden entscheiden |
| **R** esponse | Valides JSON mit 4 Feldern |

Vollständig kommentiert in Zelle 3 des Notebooks.

## Tests ausführen

```bash
pytest tests/test_analyze_email.py -v
# Erwartet: 4 passed — kein API-Key nötig (Mock-Client)
```

## Stufe 2: Live Exchange-Anbindung

### Voraussetzungen

```bash
pip install "exchangelib>=5.1.0"
```

### Nutzung

1. Notebook öffnen und alle Zellen bis einschließlich **Stufe 1** ausführen (Setup, Funktionen)
2. Stufe-2-Zellen ausführen (Import → Credential-Dialog → Live-Triage)
3. **Credential-Dialog:** Institution wählen, Benutzername und Passwort eingeben
4. **Verbinden** klicken — bei Erfolg: Postfach-Info erscheint, Passwort wird automatisch gelöscht
5. **Live-Triage starten** klicken

### Benutzername-Format

| Institution | Format | Beispiel |
|-------------|--------|---------|
| THWS | `vorname.nachname` | `robert.butscher` |
| DHBW | Vollständige E-Mail | `name@dhbw-mannheim.de` |

> **Hinweis DHBW:** Da DHBW-Campusse eigene Domains nutzen (dhbw-stuttgart.de, dhbw-mannheim.de usw.),
> bitte immer die vollständige E-Mail-Adresse eingeben.

### Sicherheitshinweise

- Credentials werden **niemals** in Dateien, Datenbanken oder Git gespeichert
- Passwort nur im RAM der laufenden Jupyter-Session
- Passwort wird nach erfolgreichem Login automatisch aus dem Widget gelöscht
- Kernel-Neustart → alle Credentials automatisch gelöscht

### Tests ausführen

```bash
cd UC2_Nachrichten_Triage
pytest tests/ -v
# Erwartet: 4 Tests (analyze_email) + 16 Tests (exchange_helpers) = 20 grün
```

## Nächste Schritte (Stufe 2)

- **exchangelib-Anbindung**: Live-Mails aus THWS/DHBW-Exchange-Postfach abrufen
- **Batch-Export**: Ergebnisse als CSV oder HTML-Report speichern
- **Feedback-Loop**: Korrekturen für Few-Shot-Prompts nutzen
