# DB Chat Integration — Design

**Date:** 2026-02-25
**Status:** Approved

---

## Goal

Phil erkennt Zugabfragen im Chat, extrahiert Abfahrtsort, Zielort und Zeit via LLM, holt echte HAFAS-Verbindungen, antwortet kurz im Chat und navigiert automatisch zur TrainView mit ausgefülltem Formular und sofort ausgeführter Suche.

## Constraints

- **HAFAS liefert keine Preise** — nur Verbindungen, Zeiten, Gleisinformationen. Buchung und Preisinfo verbleiben auf bahn.de.
- **Default-Abfahrtsort:** Nürnberg Hbf (hartcodiert als Fallback, wenn der Nutzer keinen nennt).
- **Kein Umbau des Chat-Endpoints** — das bestehende Context-Injection-Pattern wird erweitert, kein Tool-Use/Function-Calling.
- **Lokale und Cloud-LLMs** müssen beide funktionieren.

## Architecture

### Trigger

Regex `TRAIN_TRIGGER_RE` erkennt Zugintention an Schlüsselwörtern (Zug, Bahn, Verbindung, fahren nach, reisen nach, ICE, IC, Abfahrt, Ankunft, DB, bahn.de …).

### Zweistufige Verarbeitung

**Stufe 1 — LLM-Extraktion (non-streaming, max_tokens=80):**
Ein kurzer synchroner LLM-Call mit dem Prompt:

```
Extrahiere aus der folgenden Nachricht Abfahrtsort, Zielort und gewünschte Abfahrtszeit als JSON.
Antworte NUR mit JSON, kein Text drumherum.
Format: {"from_name": "...", "to_name": "...", "when": "YYYY-MM-DDTHH:MM oder null"}
Wenn kein Abfahrtsort genannt wird, setze "from_name": "Nürnberg Hbf".
Wenn keine Zeit erkennbar ist, setze "when": null.

Nachricht: {message}
```

**Stufe 2 — HAFAS-Lookup:**
- `_hafas.locations(from_name)` → erste Station → `from_id`
- `_hafas.locations(to_name)` → erste Station → `to_id`
- `_hafas.journeys(from_id, to_id, when, max_journeys=5)` → Verbindungen

### SSE-NAV-Token

Am Ende des gestreamten Phil-Textes wird (unsichtbar) eingebettet:

```
[TRAIN_NAV:{"from_id":"...","from_name":"...","to_id":"...","to_name":"...","when":"..."}]
```

Das Frontend filtert diesen Token aus dem angezeigten Text heraus und wertet ihn separat aus.

## Data Flow

```
User message
  → TRAIN_TRIGGER_RE match
  → LLM extract → {from_name, to_name, when}
  → HAFAS locations × 2 → {from_id, to_id}
  → HAFAS journeys → 5 connections (or error)
  → Chat streams: short ack text + [TRAIN_NAV:{...}]
  → Frontend parses TRAIN_NAV
  → store.setTrainPreset({from_id, from_name, to_id, to_name, when})
  → store.setView('train')
  → TrainView mounts → useEffect → search() auto-triggered
```

## Backend Changes (`main.py`)

### New: `TRAIN_TRIGGER_RE`

```python
TRAIN_TRIGGER_RE = re.compile(
    r'\b(zug|bahn|verbindung|fahrplan|fahren nach|reisen nach|züge|bahnhof|'
    r'ICE|IC\b|regional|db\.de|bahn\.de|abfahrt|ankunft|umsteigen|gleis)\b',
    re.IGNORECASE
)
```

### New: `_extract_train_params(message: str, llm) -> dict | None`

- Non-streaming LLM call, `max_tokens=80`
- Returns `{"from_name", "to_name", "when"}` or `None` on failure
- Parses JSON strictly; returns `None` if unparseable

### New: `_build_train_nav(message: str, llm) -> str | None`

- Calls `_extract_train_params()`
- Resolves station names to IDs via `_hafas.locations()`
- Returns a `[TRAIN_NAV:{...}]` token string, or `None` on any failure
- All errors swallowed — never blocks the chat response

### In `chat()` endpoint

After web search context block, add:

```python
if TRAIN_TRIGGER_RE.search(req.message):
    try:
        nav_token = _build_train_nav(req.message, llm)
        if nav_token:
            context_str += f"\n\n[Systeminformation: Verbindungssuche vorbereitet. Füge am Ende deiner Antwort folgenden Token exakt ein: {nav_token}]"
    except Exception as exc:
        logging.warning(f"[Train] Fehler: {exc}")
```

## Frontend Changes

### `api/types.ts`

Extend `TrainPreset`:

```ts
export interface TrainPreset {
  from_id: string
  from_name: string
  to_id: string
  to_name: string
  when?: string   // ISO string, optional
}
```

### `store/useStore.ts`

`trainPreset` already exists — update type to match new `TrainPreset` shape.

### Chat SSE parser (wherever `[DONE]` is handled)

After stream completes, scan full response text for `[TRAIN_NAV:{...}]`:

```ts
const navMatch = fullText.match(/\[TRAIN_NAV:(\{.*?\})\]/)
if (navMatch) {
  const preset = JSON.parse(navMatch[1])
  useStore.getState().setTrainPreset(preset)
  useStore.getState().setView('train')
}
// Strip token from displayed text
displayText = fullText.replace(/\[TRAIN_NAV:\{.*?\}\]/, '').trim()
```

### `TrainView.tsx`

Extended `useEffect` on mount — when `trainPreset` has `from_id` + `to_id`:

```ts
useEffect(() => {
  if (trainPreset?.from_id && trainPreset?.to_id) {
    setFromStation({ id: trainPreset.from_id, name: trainPreset.from_name })
    setFromQuery(trainPreset.from_name)
    setToStation({ id: trainPreset.to_id, name: trainPreset.to_name })
    setToQuery(trainPreset.to_name)
    if (trainPreset.when) setDeparture(trainPreset.when.slice(0, 16))
    setTrainPreset(null)
    // Auto-search
    setTimeout(() => search(), 0)
  }
}, [])
```

## Error Handling

| Situation | Verhalten |
|-----------|-----------|
| LLM-Extraktion liefert kein valides JSON | Kein NAV-Token → Phil antwortet normal, kein Crash |
| HAFAS findet Bahnhof nicht | Kein NAV-Token → Phil schreibt "bitte nutze die Reiseplanung direkt" |
| HAFAS-Timeout | Kein NAV-Token, Chat-Antwort erscheint trotzdem |
| Regex-False-Positive (kein echter Zug gemeint) | LLM-Extraktion liefert `null` → kein NAV |
| `when` nicht erkennbar | `when: null` → HAFAS sucht ab jetzt |

## What HAFAS Does NOT Provide

- Preise / Ticketkosten → bahn.de-Link in der TrainView bleibt für Buchung
- Sitzplatzverfügbarkeit
- Buchungsfunktion

## Files Touched

| File | Change |
|------|--------|
| `backend/main.py` | `TRAIN_TRIGGER_RE`, `_extract_train_params()`, `_build_train_nav()`, inject in `chat()` |
| `frontend/src/api/types.ts` | Extend `TrainPreset` interface |
| `frontend/src/store/useStore.ts` | Update `trainPreset` type |
| `frontend/src/components/Chat/Chat.tsx` | Parse `[TRAIN_NAV]` token, strip from display, navigate |
| `frontend/src/components/Views/TrainView.tsx` | Extended `useEffect` for auto-search with full preset |
