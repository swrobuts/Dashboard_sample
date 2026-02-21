# UC2 Web-App Design — Nachrichten-Triage GUI

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan from this design.

**Goal:** Vollständige Web-App für UC2 Nachrichten-Triage mit animiertem Phil-Avatar, OpenAI TTS und Live-Exchange-Anbindung — deployed auf `kn-triage.butscher.cloud`.

**Status:** Approved ✅
**Datum:** 2026-02-21
**Deployment:** `kn-triage.butscher.cloud` (Docker + Traefik, butscher.cloud VPS)

---

## Vision

Die Web-App ist das öffentliche Gesicht von UC2. Sie richtet sich nicht nur an Studierende, sondern
an jeden Besucher von `showcase.butscher.cloud`. Daher gelten höchste Ansprüche an Ästhetik,
Typographie und UX — Bauhaus-Prinzipien: Reduktion, Geometrie, Form follows Function.

Der animierte Assistent "Phil" begrüßt, spricht und reagiert — wie im Knowledge Navigator 1987,
aber mit zeitlosem, modernem Design.

---

## Visuelles Design

### Designprinzipien

- **Bauhaus:** Klare Geometrie, keine Dekoration ohne Funktion, starke Typographie
- **Weißraum:** Großzügig — Luft ist kein verschwendeter Raum, sondern Gestaltungsmittel
- **Reduktion:** Farbe nur wo sie Information trägt (Prioritätskodierung)
- **Zeitlosigkeit:** Kein Trend-Design, in 10 Jahren noch schön

### Farbpalette

| Token | Wert | Verwendung |
|-------|------|------------|
| `--bg` | `#FAFAF8` | Seiten-Hintergrund (Warmweiß) |
| `--surface` | `#FFFFFF` | Karten, Panels |
| `--surface-2` | `#F4F4F0` | Input-Felder, Tabs |
| `--border` | `#E8E8E4` | Trennlinien, Rahmen |
| `--text-primary` | `#18181B` | Haupttext |
| `--text-secondary` | `#71717A` | Labels, Metadaten |
| `--text-muted` | `#A1A1AA` | Platzhalter |
| `--accent` | `#E85D04` | Phil-Akzent, CTAs, Fokus-Ring |
| `--vip` | `#DC2626` | VIP-Kategorie |
| `--aktion` | `#D97706` | Aktion nötig |
| `--info` | `#2563EB` | Nur Info |
| `--ignorieren` | `#9CA3AF` | Ignorieren |

### Typographie

```css
--font-sans: 'DM Sans', 'Inter', system-ui, sans-serif;

/* Hierarchie */
h1: 2rem / 700 / tracking: -0.02em
h2: 1.25rem / 600 / tracking: -0.01em
label: 0.75rem / 500 / uppercase / tracking: 0.08em
body: 0.9375rem / 400 / line-height: 1.6
caption: 0.8125rem / 400 / color: var(--text-secondary)
```

Fonts über Google Fonts CDN geladen: `DM+Sans:wght@400;500;600;700`.

### Spacing-System (8px Grid)

```
--space-1: 8px   --space-4: 32px
--space-2: 16px  --space-6: 48px
--space-3: 24px  --space-8: 64px
```

---

## Phil-Avatar (CSS/SVG)

### Geometrie (Bauhaus / Oskar Schlemmer)

Reines SVG mit CSS-Animationen. Kein Canvas, kein WebGL.

```svg
<!-- Kopf: Ellipse -->
<ellipse cx="60" cy="55" rx="45" ry="50" fill="#18181B"/>

<!-- Augen: zwei Kreise mit Iris -->
<circle class="eye-left"  cx="42" cy="48" r="8" fill="white"/>
<circle class="eye-right" cx="78" cy="48" r="8" fill="white"/>
<ellipse class="iris-left"  cx="44" cy="49" rx="4" ry="4" fill="#18181B"/>
<ellipse class="iris-right" cx="80" cy="49" rx="4" ry="4" fill="#18181B"/>

<!-- Mund: Rechteck, height animiert -->
<rect class="mouth" x="42" y="68" width="36" height="4" rx="2" fill="white"/>
```

### CSS-Animationszustände

| Zustand | Beschreibung |
|---------|-------------|
| `idle` | Sanftes Blinzeln alle 4s (`scaleY(0.05)` auf Iris, 120ms) |
| `speaking` | Mund-Höhe oszilliert 2–10px (8Hz, `animation: speak 0.12s ease-in-out infinite alternate`) |
| `thinking` | Augen blicken leicht nach oben-links (`translateY(-2px)`) |
| `done` | Kurzes Nicken (`translateY(3px)` auf gesamten SVG, 300ms) |

JS setzt `data-state` auf dem SVG-Wrapper; CSS reagiert auf den Attributwert.

### Audio-Synchronisation

```javascript
// Während Audio spielt: speaking-State
audio.addEventListener('play',  () => phil.dataset.state = 'speaking');
audio.addEventListener('pause', () => phil.dataset.state = 'idle');
audio.addEventListener('ended', () => {
  phil.dataset.state = 'done';
  setTimeout(() => phil.dataset.state = 'idle', 400);
});
```

---

## UI-Layout

### Zwei-Spalten-Grid (Desktop)

```
┌─────────────────────────────────────────────────────────────────┐
│  PHIL · Nachrichten-Triage                               2026   │
│  ──────────────────────────────────────────────────────────── │
├──────────────────────┬──────────────────────────────────────────┤
│                      │                                          │
│   Phil-Avatar        │   [ E-Mail einfügen ] [ Live Exchange ]  │
│   (SVG, 120×120px)   │   ──────────────────────────────────     │
│                      │                                          │
│   Sprechblase        │   Paste: Textarea                        │
│   (Typewriter-Text)  │   Exchange: Credential-Form              │
│                      │                                          │
│   ──────────────     │   [ Analysieren / Verbinden ]            │
│   Audio-Waveform     │                                          │
│   (Canvas, 120×32)   │   ──────────────────────────────────     │
│                      │   Ergebnis-Karten (expandierbar)         │
│   [▶] [⏸] [⏹]       │                                          │
│                      │                                          │
└──────────────────────┴──────────────────────────────────────────┘

Spalte links:  320px, sticky beim Scrollen
Spalte rechts: flex-1, max-width 720px
Gesamt:        max-width 1100px, margin: 0 auto
```

### Mobile (< 768px)

Phil-Avatar oben zentriert (80×80px), darunter Sprechblase, darunter die Karten — single column.

### Ergebnis-Karten

```
┌──────────────────────────────────────────────────────────────┐
│ ▐████ VIP                                    Priorität 1  [▶]│  ← 4px left border in --vip
│       Dekan fordert Stellungnahme bis 18 Uhr.                │
│       Prüfungsausschuss tagt morgen.                         │
│                                               ▼ Details      │  ← expandiert bei Klick
├ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ┤
│  Empfehlung: Sofort Bewertungsunterlagen suchen und          │
│  schriftliche Stellungnahme verfassen.                       │
│                                                              │
│  Von: dekan@thws.de  ·  Empfangen: heute 09:14              │
└──────────────────────────────────────────────────────────────┘
```

- `border-left: 4px solid var(--vip)` als einziges Farbelement
- `border-radius: 12px`, `box-shadow: 0 1px 4px rgba(0,0,0,0.06)`
- Expansion: `max-height` Transition (300ms ease), kein Layout-Shift
- `▶`-Button: Phil liest diese Karte vor (TTS)

### Sprechblase (Phil)

```
╭─────────────────────────╮
│ Sie haben 12 neue       │
│ Nachrichten. 3 sind     │
│ dringend.               │
╰────╮────────────────────╯
     │ (Pfeil zeigt auf Phil)
```

- Typewriter-Effekt: Zeichen werden einzeln eingefügt (20ms/Zeichen)
- Gleichzeitig spielt TTS-Audio
- Max. 2 Zeilen sichtbar, danach fade-out

---

## Interaktionsfluss

### Mode A: E-Mail einfügen (Paste)

```
1. Nutzer öffnet Seite
   → Phil: idle-Animation, Sprechblase leer

2. Nutzer fügt E-Mail ein, klickt "Analysieren"
   → Phil: thinking-State
   → POST /api/analyze → Triage-JSON

3. Antwort kommt zurück
   → POST /api/tts (Opening-Summary-Text) → MP3
   → Phil: speaking-State, Audio spielt, Sprechblase tippt
   → Ergebnis-Karten erscheinen (staggered fade-in, 80ms Versatz)

4. Nutzer klickt [▶] auf einer Karte
   → POST /api/tts (Karten-Zusammenfassung) → MP3
   → Phil: speaking-State, liest vor
```

### Mode B: Live Exchange

```
1. Nutzer wechselt zu Tab "Live Exchange"
   → Credential-Form erscheint (Institution, Benutzername, Passwort)

2. Nutzer klickt "Verbinden"
   → POST /api/exchange/connect → session_id als httpOnly-Cookie
   → Erfolg: Form verschwindet, "Verbunden mit THWS" + Postfach-Info
   → Phil: "Verbindung hergestellt. Lade Nachrichten..."

3. Nutzer klickt "Live-Triage starten"
   → POST /api/exchange/fetch → E-Mail-Liste
   → POST /api/analyze (für jede Mail, sequentiell)
   → Karten erscheinen progressiv

4. Nutzer klickt "Trennen"
   → POST /api/exchange/disconnect → Cookie gelöscht
   → Phil: "Verbindung getrennt."
```

---

## Backend-API (FastAPI)

### Endpunkte

| Method | Path | Input | Output |
|--------|------|-------|--------|
| `POST` | `/api/analyze` | `{email_text: str}` | `{kategorie, priorität, zusammenfassung, empfohlene_aktion}` |
| `POST` | `/api/tts` | `{text: str}` | `audio/mpeg` (streaming) |
| `POST` | `/api/exchange/connect` | `{username, password, institution}` | `{status, inbox_count}` + httpOnly-Cookie |
| `POST` | `/api/exchange/fetch` | Cookie | `[{subject, sender, body, datetime_received}]` |
| `POST` | `/api/exchange/disconnect` | Cookie | `{status: "ok"}` |
| `GET` | `/health` | — | `{status: "ok"}` |

### Session-Management

```python
# In-memory, kein Redis, kein DB
sessions: dict[str, Account] = {}

# Session-ID: UUID4, httpOnly-Cookie, SameSite=Strict
# Lifetime: bis Server-Restart oder explizitem /disconnect
```

### TTS (OpenAI)

```python
from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

response = client.audio.speech.create(
    model="tts-1",
    voice="onyx",       # Warm, professionell, deutsch-tauglich
    input=text,
    response_format="mp3",
)
# StreamingResponse zurück an den Browser
```

---

## Sicherheit

| Aspekt | Maßnahme |
|--------|----------|
| API-Keys | Nur in `.env`, nie im Frontend oder Logs |
| Exchange-Credentials | Nur im Backend-RAM, nie in Logs, nie in Response |
| Session-Cookie | `httpOnly=True`, `SameSite="Strict"`, `Secure=True` |
| HTTPS | Traefik erzwingt Redirect HTTP→HTTPS |
| CORS | Nur `kn-triage.butscher.cloud` als Origin erlaubt |
| Password-Feld | `type="password"` im Browser, autocomplete=off |
| Server-Restart | Löscht alle Sessions automatisch |

---

## Datei- und Ordnerstruktur

```
UC2_Nachrichten_Triage/
├── webapp/
│   ├── frontend/
│   │   ├── index.html          ← Einzige HTML-Datei
│   │   ├── style.css           ← Alle Styles (CSS Custom Properties)
│   │   └── app.js              ← Alle Client-Logik (vanilla JS, ES Modules)
│   ├── backend/
│   │   ├── main.py             ← FastAPI App
│   │   ├── exchange_helpers.py ← Kopie aus UC2-Root
│   │   ├── requirements.txt    ← anthropic, openai, exchangelib, fastapi, uvicorn
│   │   └── .env.example        ← ANTHROPIC_API_KEY, OPENAI_API_KEY
│   ├── Dockerfile              ← Multi-stage: frontend static + uvicorn
│   └── docker-compose.yml      ← Traefik-Labels für kn-triage.butscher.cloud
├── nachrichten_triage.ipynb    ← unberührt
└── exchange_helpers.py         ← unberührt
```

### Docker-Setup

```dockerfile
# Dockerfile (single service: FastAPI serviert auch das Frontend als StaticFiles)
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ ./backend/
COPY frontend/ ./frontend/
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

FastAPI serviert `frontend/` als `StaticFiles` unter `/` — kein separater nginx nötig.

```yaml
# docker-compose.yml (Traefik-ready)
services:
  triage:
    build: .
    env_file: backend/.env
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.triage.rule=Host(`kn-triage.butscher.cloud`)"
      - "traefik.http.routers.triage.tls.certresolver=letsencrypt"
```

---

## Testing

| Test | Art | Tool |
|------|-----|------|
| `/api/analyze` Endpunkt | Unit (Mock Claude) | pytest |
| `/api/tts` Endpunkt | Unit (Mock OpenAI) | pytest |
| Exchange connect/fetch/disconnect | Unit (Mock exchangelib) | pytest |
| Phil-Avatar Animationszustände | Manual | Browser DevTools |
| TTS-Synchronisation | Manual | Browser |
| Mobile Layout | Manual | Chrome DevTools |
| HTTPS + Cookie | Manual | curl / Browser |

---

## Nicht im Scope

- Authentifizierung / Login für die Web-App selbst (öffentlich zugänglich)
- Persistenz (kein DB, kein localStorage für Triage-Ergebnisse)
- Batch-Export (CSV/PDF) — Folge-Feature
- Dark Mode — Folge-Feature
- i18n / mehrsprachig — immer Deutsch
