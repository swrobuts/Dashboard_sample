# Knowledge Navigator Use Cases — Master Design Document

**Kurs:** Datenbasierte Fallstudien / KI-Kompetenz
**Hochschule:** THWS Business School / DHBW
**Dozent:** Prof. Dr. Robert Butscher
**Datum:** 2026-02-21
**Status:** Approved ✅

---

## Vision & Kontext

Apple zeigte 1987 im Knowledge Navigator Konzeptvideo 7 Use Cases eines KI-Assistenten —
damals Science-Fiction, heute technisch umsetzbar. Wir implementieren 6 davon
(UC5 Videokonferenz = heute Teams/Zoom) schrittweise mit Studierenden.

**Meta-Pointe für die Lehre:**
> 1987 hatte EIN Assistent EINEN Professor. 2026 hat JEDER Student so einen Assistenten
> in der Hosentasche — kostenlos.

**Thematischer roter Faden:** Abholzung des Amazonas-Regenwalds
(aus dem Originalvideo) verbindet UC3, UC4 und UC7.

---

## Ordnerstruktur

```
Knowledge Navigator Use Cases/
├── UC1_Tagesueberblick/
├── UC2_Nachrichten_Triage/
├── UC3_Literaturrecherche/          ← Amazon: Paper suchen
├── UC4_Interaktive_Datenvisualisierung/  ← Amazon: Daten visualisieren
│   (UC5 Videokonferenz → gestrichen, heute: Teams/Zoom)
├── UC6_Sprachgesteuerte_Aufgabendelegation/
├── UC7_Autonomes_Agieren/           ← Amazon: Agent agiert autonom
├── Bonus_Handwriting_Recognition/
└── docs/plans/
```

---

## Tech Stack

| Technologie | Zweck |
|-------------|-------|
| Python + Jupyter Notebooks | Alle Python-Projekte |
| Deepnote | Deployment Python-Projekte |
| HTML / CSS / JavaScript | Frontend-Projekte |
| Docker + Docker Compose | Containerisierung |
| Traefik (butscher.cloud) | Reverse Proxy + SSL + Subdomains |
| Claude API (Anthropic) | LLM-Kern für alle Use Cases |
| OpenAI API | Alternative + TTS (gpt-4o-audio) |
| HuggingFace / Whisper | STT + Open-Source Modelle |
| exchangelib (Python) | Exchange-Anbindung via EWS (User/Passwort) |
| imaplib (Python built-in) | Fallback: IMAP-Mailzugriff |
| Global Forest Watch API | Amazon-Abholzungsdaten (UC3, UC4, UC7) |
| Semantic Scholar API | Literaturrecherche (UC3) |
| Open-Meteo API | Wetter (UC1, kostenlos, kein Key nötig) |

**Lokale Entwicklung:** PyCharm / DataSpell
**Versionierung:** Git (dieses Repo)

---

## Prompting-Strategie (CO-STAR + Chain-of-Thought)

Alle LLM-Aufrufe folgen dem CO-STAR-Framework:

```
C — Context:    Hintergrund und Rolle des Assistenten
O — Objective:  Was soll konkret erreicht werden?
S — Style:      Ton, Sprache, Format der Antwort
T — Tone:       Formell / informell / akademisch
A — Audience:   An wen richtet sich die Ausgabe?
R — Response:   Gewünschtes Ausgabeformat (JSON, Markdown, Plain Text)
```

**Chain-of-Thought:** Komplexe Aufgaben mit expliziten Denkschritten:
`"Analysiere Schritt für Schritt: 1) ... 2) ... 3) ..."`

Jedes Projekt enthält ein dokumentiertes **Prompt-Template** mit Kommentaren im Code.

---

## Exchange Credential-Dialog (UC1 + UC2 + UC6 + UC7)

Gemeinsamer Auth-Helper für alle Exchange-verbundenen Use Cases:

```
┌─────────────────────────────────────────┐
│  🔐  Exchange-Verbindung                │
├─────────────────────────────────────────┤
│  Institution  [ THWS ▼ | DHBW ]        │
│  Benutzername [ vorname.nachname      ] │
│  Passwort     [ ••••••••••••••••••••• ] │
│                                         │
│  ⚠ Ihre Daten werden nicht gespeichert │
│  [ Verbinden ]   [ Abbrechen ]          │
└─────────────────────────────────────────┘
```

**Sicherheitsprinzipien:**
- Credentials **niemals** in Dateien, Datenbanken oder Git
- Nur im RAM der laufenden Session
- Passwort immer `type="password"` (masked)
- HTTPS-only im Deployment (Traefik SSL)
- Lehrprinzip: Studis lernen von Tag 1, keine Credentials in Code

---

## Deployment-Architektur

```
butscher.cloud (VPS)
├── Traefik (Reverse Proxy + SSL)
├── showcase.butscher.cloud          → Showcase-Page (alle Use Cases)
├── kn-phil.butscher.cloud           → UC1: Tagesüberblick (Phil)
├── kn-triage.butscher.cloud         → UC2: Nachrichten-Triage
├── kn-voice.butscher.cloud          → UC6: Aufgabendelegation
└── kn-hwrecog.butscher.cloud        → Bonus: Handwriting Recognition

Deepnote (Cloud Notebooks)
├── UC3: Literaturrecherche (Amazon-Paper)
├── UC4: Interaktive Datenvisualisierung (Amazon-Karte)
└── UC7: Autonomes Agieren (Amazon-Agent)
```

---

## Use Cases — Detail

### Phase 1 — Einstieg

#### UC2: Nachrichten-Triage
**Original 1987:** Phil spielt 3 Nachrichten ab (Guatemala-Team, Student Jordan, Mutter).
**2026:** KI liest Mails, kategorisiert nach Priorität, fasst zusammen.

- **Demo-Idee:** 20 Mails → Bot sortiert in VIP / Aktion nötig / Nur Info / Ignorieren
- **Stufe 1:** Paste-Modus (E-Mail-Text einfügen, kein Exchange nötig) → perfekter Einstieg
- **Stufe 2:** exchangelib-Anbindung (Live-Mails aus THWS/DHBW-Postfach)
- **Tech:** Python, Claude API, exchangelib (Stufe 2), Jupyter Notebook
- **Deployment:** Deepnote
- **Schwierigkeit:** ⭐ Einfach (Stufe 1) → ⭐⭐⭐ Mittel (Stufe 2)
- **Lernziele:** API-Calls, CO-STAR-Prompting, JSON-Output, Kategorisierung

**CO-STAR Template:**
```
C: Du bist ein intelligenter E-Mail-Assistent für einen Hochschulprofessor.
O: Analysiere die folgende E-Mail und kategorisiere sie.
S: Strukturiert, präzise, ohne Füllwörter.
T: Professionell, sachlich.
A: Der Dozent, der schnell entscheiden will, welche Mails er lesen muss.
R: JSON mit Feldern: kategorie, priorität, zusammenfassung (max. 2 Sätze), empfohlene_aktion
```

---

#### UC1: Tagesüberblick ("Phil")
**Original 1987:** "You have three messages." Phil gibt Überblick: Lunch 12:00, Kathy zum Flughafen 14:00, Vorlesung 16:15.
**2026:** Bot fasst Kalender + Mails + Wetter in einer Morgenantwort zusammen. TTS liest es vor.

- **Demo-Idee:** "Was steht heute an?" → Kalender + Mails + Wetter in einer gesprochenen Antwort
- **Tech:** Python, exchangelib (Kalender + Mails), Open-Meteo API (Wetter, kostenlos),
  OpenAI TTS oder gTTS, HTML-UI mit Credential-Dialog
- **Deployment:** Docker → kn-phil.butscher.cloud
- **Schwierigkeit:** ⭐⭐⭐ Mittel
- **Lernziele:** API-Komposition, TTS, exchangelib, Prompt-Aggregation

---

### Phase 2 — Aufbauend

#### UC3: Literaturrecherche (🌿 Amazon-Thread)
**Original 1987:** "Pull up all the new articles I haven't read yet. Journal articles only."
**2026:** Semantic Scholar / Perplexity API für automatische Paper-Suche zum Amazonas.

- **Demo-Idee:** "Zeig mir aktuelle Paper zur Abholzung des Amazonas" →
  API-Suche → LLM-Zusammenfassung mit Quellen
- **Tech:** Python, Semantic Scholar API (kostenlos), Claude API (Zusammenfassung + RAG),
  ChromaDB/FAISS (Vector Store), Jupyter Notebook
- **Deployment:** Deepnote
- **Schwierigkeit:** ⭐⭐⭐ Mittel-hoch
- **Lernziele:** Web-APIs, Embeddings, RAG-Pipeline, Quellenangaben
- **Hinweis:** Baut auf ../RAG/ Projekt im Repo auf

#### UC4: Interaktive Datenvisualisierung (🌿 Amazon-Thread)
**Original 1987:** Weltkarte → "Show Brazil" → "Copy the last 30 years at 1 month intervals"
→ Zeitreihen-Animation der Abholzung.
**2026:** Global Forest Watch API + Plotly/Folium → interaktive Karte + Zeitreihe.

- **Demo-Idee:** "Zeig mir die Abholzung im Amazonas über 30 Jahre" →
  KI generiert Visualisierung mit echten Daten
- **Tech:** Python, Global Forest Watch API (oder INPE PRODES), Plotly, Folium,
  Claude API (Code Generation), Pandas, Jupyter Notebook
- **Deployment:** Deepnote (interaktive Notebooks)
- **Schwierigkeit:** ⭐⭐ Mittel
- **Lernziele:** Open Data APIs, Plotly/Folium, LLM-gestützte Code-Generierung, Geodaten

**Daten-APIs:**
| API | Daten | Zugang |
|-----|-------|--------|
| Global Forest Watch | Waldverlust 2000-heute | Kostenlos |
| INPE PRODES | Brasilianische Abholzungsdaten | Kostenlos |
| NASA FIRMS | Feuer/Abholzung Satellitendaten | Kostenlos |

---

### Phase 3 — Fortgeschritten

#### UC6: Sprachgesteuerte Aufgabendelegation
**Original 1987:** "Print this article." → "If Kathy calls, tell her I'll be there at 2:00."
→ "Find out if I can set up a meeting tomorrow with Tom Lee."
**2026:** Voice-Input → LLM erkennt Intent → führt Aktionen aus.

- **Demo-Idee:** Per Sprache drei Befehle → Bot erkennt Intent und führt alle aus
- **Tech:** HTML/JS (Web Speech API für Browser-STT), Python Backend (FastAPI),
  Whisper (Fallback STT), Claude API (Intent Recognition + Action Planning),
  exchangelib (Kalender-Aktionen)
- **Deployment:** Docker → kn-voice.butscher.cloud
- **Schwierigkeit:** ⭐⭐⭐⭐ Hoch
- **Lernziele:** STT, Intent Recognition, Multi-Action-Chains, FastAPI

#### UC7: Autonomes Agieren (🌿 Amazon-Thread)
**Original 1987:** Professor verlässt den Raum. Phil übernimmt autonom: nimmt Anrufe entgegen,
leitet Nachrichten weiter, arbeitet Aufgaben ab.
**2026:** Agentic AI — Bot beantwortet eigenständig Mails, koordiniert Termine,
und: analysiert + simuliert Amazon-Abholzungsdaten autonom.

- **Demo-Idee:** Bot (1) antwortet auf Studi-Mail, (2) koordiniert Termin via cal.com,
  (3) aktualisiert Amazon-Datenlage und erstellt Prognose — alles ohne Eingriff
- **Tech:** Python, Claude API (Agents / Tool Use), exchangelib, Global Forest Watch API,
  Plotly (Simulation-Output), Jupyter Notebook
- **Deployment:** Deepnote
- **Schwierigkeit:** ⭐⭐⭐⭐⭐ Sehr hoch
- **Lernziele:** Agentic AI, Tool Use / Function Calling, autonome Entscheidungsketten

---

#### Bonus: Handwriting Recognition
- **Beschreibung:** Canvas-Zeichenfläche → HuggingFace TrOCR → erkannter Text
- **Tech:** HTML/JS Canvas, Python Backend (FastAPI), TrOCR (HuggingFace)
- **Deployment:** Docker → kn-hwrecog.butscher.cloud
- **Schwierigkeit:** ⭐⭐⭐ Mittel-hoch
- **Lernziele:** HuggingFace Inference, Canvas API, REST-Backend

---

## Showcase-Dokumentation

**URL:** showcase.butscher.cloud
**Format:** Interaktive HTML-Landing-Page mit Use-Case-Cards

**Inhalt pro Use Case:**
- Originalszene aus dem KN-Video (1987) + heutige Umsetzung
- Eingesetzte Tools & Technologien (als Badges)
- CO-STAR Prompt-Template (aufklappbar)
- Live-Demo-Link / Deepnote-Link
- Code-Snippets (Syntax-highlighted)
- Lernziele & Schwierigkeitsgrad (⭐ Skala)

**Seitenstruktur:**
- Hero: "Von der Vision zur Realität — Knowledge Navigator 1987 → 2026"
- Amazon-Banner: roter Faden UC3/UC4/UC7 hervorgehoben
- Use-Case-Cards mit Filter (Phase / Technologie / Schwierigkeit)
- Footer: THWS Business School, Prof. Dr. Robert Butscher, SS 2026

---

## Skills-Einsatz

| Phase | Skills |
|-------|--------|
| Planung | `superpowers:writing-plans`, `superpowers:brainstorming` |
| Frontend/UI | `frontend-design` |
| Implementierung | `claude-developer-platform`, `superpowers:test-driven-development` |
| QS / Review | `code-review:code-review`, `superpowers:requesting-code-review` |
| Deployment | `superpowers:verification-before-completion` |
| Debugging | `superpowers:systematic-debugging` |
| Git | `commit-commands:commit`, `commit-commands:commit-push-pr` |
| Parallelisierung | `superpowers:dispatching-parallel-agents` |

---

## Arbeitsweise

1. Pro Use Case: Implementierungsplan via `superpowers:writing-plans`
2. Schrittweise — nach jedem Schritt Feedback des Dozenten abwarten
3. Code Review via `code-review:code-review` vor Deployment
4. `superpowers:verification-before-completion` vor Go-Live
5. Dokumentation parallel zur Implementierung
6. Commits nach jedem abgeschlossenen Schritt

---

## Nächster Schritt

**→ UC2: Nachrichten-Triage, Stufe 1** (Paste-Modus, kein Exchange nötig)
Implementierungsplan via `superpowers:writing-plans`.
