# UC3 Meeting-Vorbereitung — Design

**Datum:** 2026-02-22
**Status:** Approved

---

## Ziel

Wenn ein Kalendertermin angeklickt wird, schlägt Phil proaktiv vor, ein Meeting-Briefing zu erstellen. Ein Klick liefert strukturiert: Teilnehmer, offene Mails, letzte Interaktion und einen Agenda-Vorschlag.

---

## UX-Flow

1. User klickt Kalendertermin → Edit-Modal öffnet sich + PhilPanel bekommt den Termin als `selection`
2. PhilPanel erkennt `selection.type === 'calendar'` und Termin liegt ≤ 7 Tage in der Zukunft (oder heute) → zeigt **Briefing-Banner** als hervorgehobenen Button über den normalen Quick-Actions
3. User klickt Banner → Frontend ruft `POST /api/briefing` auf
4. Backend streamt strukturiertes Briefing als SSE
5. Phil-Antwort erscheint im normalen Chat-Bereich (gleiche Streaming-Infrastruktur)

---

## Architektur

### Neue/geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `backend/main.py` | Neuer `POST /api/briefing`-Endpoint |
| `frontend/src/api/client.ts` | `briefingStream(event)` Methode |
| `frontend/src/api/types.ts` | `BriefingRequest`-Typ (optional, inline reicht) |
| `frontend/src/components/Phil/PhilPanel.tsx` | Briefing-Banner + Stream-Aufruf |
| `frontend/src/components/Phil/PhilPanel.module.css` | Styling für Briefing-Banner |

---

## Backend: `POST /api/briefing`

### Request

```json
{
  "subject": "Austausch mit Kai Hufnagel",
  "start": "2026-02-24T10:00:00+01:00",
  "end": "2026-02-24T11:00:00+01:00",
  "location": "Büro 3.12",
  "body": ""
}
```

### Logik (sequenziell)

1. **Personen extrahieren** — Regex auf `subject`:
   `r'\bmit\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)+)'`
   Ergibt z.B. `"Kai Hufnagel"`

2. **RAG-Suche** — `knowledge_store.search(query=subject, n=5)` → Liste ähnlicher Mails mit Betreff, Sender, Datum, Score. Filtert auf Score ≥ 0.60.

3. **LLM-Prompt** — System-Prompt erzwingt Markdown-Struktur:

```
Du bist PHIL, ein persönlicher Assistent. Erstelle ein kompaktes Meeting-Briefing auf Deutsch.
Verwende exakt diese Markdown-Struktur, keine Abweichungen:

## 👤 Teilnehmer
<Namen aus dem Termin>

## 📬 Letzte Mails
<Relevante Mails aus dem Kontext, oder "Keine gefunden.">

## 📋 Agenda-Vorschlag
<3–5 konkrete Punkte basierend auf Termin und Mails>

Sei prägnant. Maximal 200 Wörter insgesamt.
```

   User-Prompt enthält: Termindetails (Betreff, Datum, Uhrzeit, Ort) + RAG-Ergebnisse als strukturierten Kontext.

4. **Streaming** — `StreamingResponse` mit SSE (`data: ...\n\n`), identisch zu `/api/chat`. Nutzt `llm.stream(task="chat", ...)`.

### Pydantic-Modell

```python
class BriefingRequest(BaseModel):
    subject: str
    start: str = ""
    end: str = ""
    location: str = ""
    body: str = ""
```

---

## Frontend: PhilPanel-Änderungen

### Briefing-Banner

- Wird angezeigt wenn: `selection?.type === 'calendar'` AND Termin liegt heute oder in ≤ 7 Tagen
- Zustandsvariable `briefingDone: boolean` — nach Klick auf Banner wird `briefingDone = true` und der Banner verschwindet
- Reset von `briefingDone` bei neuem `selection` (via `useEffect` auf `selection`)

### Trigger-Button (über Quick-Actions)

```
┌─────────────────────────────────────────────────────┐
│ 📋 Meeting-Briefing für "[Terminname gekürzt]"      │
│                    [Vorbereitung erstellen →]        │
└─────────────────────────────────────────────────────┘
```

### Stream-Aufruf

Identisch zu `send()`, aber ruft `api.briefingStream(event)` statt `api.chatStream()` auf.
RAG-Block zeigt die gefundenen Mails (bereits vorhanden).

### `api.briefingStream()`

```typescript
briefingStream: (event: CalendarItem): ReadableStream<string> => {
  // POST /api/briefing, SSE parsing identisch zu chatStream
}
```

---

## Trigger-Bedingung (wann Banner erscheint)

```typescript
const isSoon = selection?.type === 'calendar' && (() => {
  const start = selection.item.start ? new Date(selection.item.start) : null
  if (!start) return false
  const diff = (start.getTime() - Date.now()) / (1000 * 60 * 60 * 24)
  return diff >= -0.5 && diff <= 7   // heute oder bis 7 Tage in der Zukunft
})()
const showBriefingBanner = isSoon && !briefingDone
```

---

## Error Handling

- Kein `knowledge_store` → RAG-Abschnitt im Prompt wird übersprungen (kein Fehler)
- LLM nicht erreichbar → Cloud-Fallback (bereits in `llm.stream()` implementiert)
- Kein Name im Betreff erkennbar → Briefing trotzdem erstellen, Teilnehmer-Abschnitt sagt „Keine Teilnehmer erkannt"

---

## Was nicht gebaut wird (YAGNI)

- Kein Abruf von Google Calendar Attendees via gog CLI (zu aufwändig, Personenextraktion aus Titel reicht)
- Kein persistentes Speichern von Briefings
- Keine Änderung am Edit-Modal
- Kein separates Briefing-Panel (nutzt bestehenden Chat-Bereich)
