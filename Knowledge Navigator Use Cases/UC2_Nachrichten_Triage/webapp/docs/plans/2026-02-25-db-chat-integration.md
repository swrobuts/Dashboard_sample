# DB Chat Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Phil detects train queries in chat, extracts route + time via LLM, fetches real HAFAS connections, answers briefly, and auto-navigates to TrainView with prefilled form and immediate search.

**Architecture:** Two-phase pattern matching the existing web-search approach: `TRAIN_TRIGGER_RE` detects intent, a synchronous `llm.create()` call extracts `{from_name, to_name, when}` as JSON, HAFAS resolves names to IDs, and a `[TRAIN_NAV:{...}]` token is embedded in the Phil system instruction so the frontend can parse it and navigate. Default departure: Nürnberg Hbf.

**Tech Stack:** Python/FastAPI backend (`backend/main.py`, `backend/llm_client.py`), PyHafas (already wired), React/TypeScript frontend (`PhilPanel.tsx`, `TrainView.tsx`, `useStore.ts`, `api/types.ts`)

---

## Context you need to understand before touching anything

**Existing HAFAS endpoints** (already working, don't touch):
- `GET /api/trains/stations?q=...` → `{"stations": [{"id": "...", "name": "..."}]}`
- `GET /api/trains/journeys?from_id=...&to_id=...&when=...` → `{"journeys": [...]}`
- `_hafas = HafasClient(NVVProfile())` — global singleton at the bottom of `main.py`

**Existing web-search pattern** (mirror this exactly for trains):
```python
# main.py ~line 1074
if WEB_SEARCH_TRIGGER_RE.search(req.message):
    try:
        web_str, web_results = build_web_context(req.message)
        if web_str:
            context_str += web_str
    except Exception as exc:
        logging.warning(f"[Memory] Web-Suche fehlgeschlagen: {exc}")
```

**LLM client** has a synchronous `.create(task, prompt, max_tokens, system)` method — use this (not `.stream()`) for parameter extraction. `task="triage"` runs locally in hybrid mode (fast, cheap).

**`llm = _get_llm(session)` is at line 1095**, after `user_msg` is built at line 1092. The train block goes between these two.

**SSE stream parsing** is in `PhilPanel.tsx` in the `send()` function. `philText` accumulates all chunks. The `finally` block (after the while-loop reader) is where TRAIN_NAV should be parsed.

**`trainPreset` in store** is currently `{ to: string } | null` — needs to be extended to the full `TrainPreset` type defined in Task 2.

**HAFAS returns `price: null` always** — don't show prices anywhere. This is by design.

---

## Task 1: Backend — TRAIN_TRIGGER_RE + helper functions

**Files:**
- Modify: `Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/backend/main.py`

### Step 1: Find the right location in main.py

Open `backend/main.py`. Find the line:
```python
# ── DB HAFAS Train Planner (via pyHafas + NVV profile) ──────────────────────
```
This is around line 1357. You will add the new train functions BEFORE this block (above it), but AFTER the `WEB_SEARCH_TRIGGER_RE` import and web search functions (around line 28).

Actually: add the new code block between the web-search block (ends ~line 1090) and the `user_msg` line (~line 1092). The helper functions go at module level, near the `_hafas` usage — add them just above `# ── DB HAFAS Train Planner`.

### Step 2: Add TRAIN_TRIGGER_RE at module level

Find this line near the top of `main.py` (around line 28):
```python
from backend.web_search import WEB_SEARCH_TRIGGER_RE, build_web_context
```

Add directly below it:
```python
import re as _re
TRAIN_TRIGGER_RE = _re.compile(
    r'\b(zug|züge|bahn|verbindung|fahrplan|fahren nach|reisen nach|bahnhof|'
    r'ICE|IC\b|regional|db\.de|bahn\.de|abfahrt|ankunft|umsteigen|gleis|'
    r'wann fährt|welche verbindung|nächster zug)\b',
    _re.IGNORECASE,
)
```

Note: `re` is almost certainly already imported in `main.py`. Check first — if `import re` already exists, just add the pattern without the `import re as _re` line and use `re.compile(...)` instead.

### Step 3: Add TaskKind "train_extract" to llm_client.py

Open `backend/llm_client.py`. Find:
```python
TaskKind = Literal["triage", "attachment_summary", "entities", "chat", "graph"]
```

Replace with:
```python
TaskKind = Literal["triage", "attachment_summary", "entities", "chat", "graph", "train_extract"]
```

Find:
```python
_LOCAL_TASKS: set[TaskKind] = {"triage", "attachment_summary"}
```

Replace with:
```python
_LOCAL_TASKS: set[TaskKind] = {"triage", "attachment_summary", "train_extract"}
```

### Step 4: Add helper functions to main.py

Add these two functions just ABOVE the line `# ── DB HAFAS Train Planner (via pyHafas + NVV profile) ──────────────────────` in `main.py`:

```python
# ── Train chat integration ─────────────────────────────────────────────────

_DEFAULT_FROM_NAME = "Nürnberg Hbf"

_TRAIN_EXTRACT_SYSTEM = (
    "Du bist ein Parameterextraktor. Antworte NUR mit einem JSON-Objekt, "
    "kein Text davor oder danach, keine Markdown-Fences. "
    "Extrahiere Abfahrtsort, Zielort und Abfahrtszeit aus der Nachricht. "
    f"Wenn kein Abfahrtsort genannt wird, setze from_name: \"{_DEFAULT_FROM_NAME}\". "
    "Wenn keine Zeit erkennbar ist, setze when: null. "
    f"Heutiges Datum: {{today}}. "
    'Format: {{"from_name": "...", "to_name": "...", "when": "YYYY-MM-DDTHH:MM oder null"}}'
)


def _extract_train_params(message: str, llm) -> dict | None:
    """Kurzer LLM-Call um from_name, to_name, when aus der Nachricht zu extrahieren.

    Returns dict with keys from_name, to_name, when (ISO string or None),
    or None if extraction fails.
    """
    import json as _json
    from datetime import date as _date
    today = _date.today().isoformat()
    system = _TRAIN_EXTRACT_SYSTEM.format(today=today)
    try:
        raw = llm.create(task="train_extract", prompt=message, max_tokens=80, system=system)
        # Strip markdown fences if LLM wraps in ```json
        raw = raw.strip()
        if raw.startswith("```"):
            import re as _re2
            raw = _re2.sub(r"^```(?:json)?\s*", "", raw)
            raw = _re2.sub(r"\s*```$", "", raw)
            raw = raw.strip()
        params = _json.loads(raw)
        if not isinstance(params.get("to_name"), str) or not params["to_name"].strip():
            return None
        if not isinstance(params.get("from_name"), str) or not params["from_name"].strip():
            params["from_name"] = _DEFAULT_FROM_NAME
        return params
    except Exception as exc:
        logging.warning(f"[Train] Parameterextraktion fehlgeschlagen: {exc}")
        return None


def _build_train_nav(message: str, llm) -> str | None:
    """Extrahiert Route aus message, löst Bahnhofsnamen via HAFAS auf,
    gibt einen [TRAIN_NAV:{...}] Token zurück oder None bei Fehler.
    """
    import json as _json
    params = _extract_train_params(message, llm)
    if not params:
        return None

    try:
        from_stations = _hafas.locations(params["from_name"])
        to_stations = _hafas.locations(params["to_name"])
    except Exception as exc:
        logging.warning(f"[Train] HAFAS locations fehlgeschlagen: {exc}")
        return None

    if not from_stations or not to_stations:
        logging.warning(f"[Train] Bahnhof nicht gefunden: {params}")
        return None

    from_s = from_stations[0]
    to_s = to_stations[0]

    nav = {
        "from_id": from_s.id,
        "from_name": from_s.name,
        "to_id": to_s.id,
        "to_name": to_s.name,
        "when": params.get("when"),
    }
    return f"[TRAIN_NAV:{_json.dumps(nav, ensure_ascii=False)}]"
```

### Step 5: Inject into chat() endpoint

In `main.py`, find this exact block (around line 1092–1095):
```python
    user_msg = (context_str + "\n\n" + req.message) if context_str else req.message

    # ── LLM-Client für diese Session ──────────────────────────────────
    llm = _get_llm(session)
```

Replace with:
```python
    user_msg = (context_str + "\n\n" + req.message) if context_str else req.message

    # ── LLM-Client für diese Session ──────────────────────────────────
    llm = _get_llm(session)

    # Train: detect and embed NAV token for frontend navigation
    if TRAIN_TRIGGER_RE.search(req.message):
        try:
            _train_nav = _build_train_nav(req.message, llm)
            if _train_nav:
                user_msg += (
                    f"\n\n[Systeminformation: Zugverbindung wurde abgerufen. "
                    f"Füge am Ende deiner Antwort diesen Token exakt ein (ohne Änderungen): {_train_nav}]"
                )
        except Exception as exc:
            logging.warning(f"[Train] NAV fehlgeschlagen: {exc}")
```

### Step 6: Manually test backend

Start the backend: `uvicorn backend.main:app --reload --port 8000`

In a browser or curl, confirm existing endpoints still work:
```bash
curl "http://localhost:8000/api/trains/stations?q=Nürnberg" -b "session_id=..."
```

Expected: JSON with stations including Nürnberg Hbf.

### Step 7: Commit

```bash
git add "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/backend/main.py"
git add "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/backend/llm_client.py"
git commit -m "feat(train): TRAIN_TRIGGER_RE + _extract_train_params + _build_train_nav"
```

---

## Task 2: Frontend — TrainPreset type + store

**Files:**
- Modify: `Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend/src/api/types.ts`
- Modify: `Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend/src/store/useStore.ts`

### Step 1: Add TrainPreset to types.ts

Open `frontend/src/api/types.ts`. Find:
```typescript
export interface TrainStation {
  id: string
  name: string
}
```

Add this new interface directly above `TrainStation`:
```typescript
export interface TrainPreset {
  from_id: string
  from_name: string
  to_id: string
  to_name: string
  when?: string | null   // ISO datetime string, optional
}
```

### Step 2: Update useStore.ts — type declaration

Open `frontend/src/store/useStore.ts`. Find:
```typescript
  trainPreset: { to: string } | null
  setTrainPreset: (p: { to: string } | null) => void
```

Replace with:
```typescript
  trainPreset: TrainPreset | null
  setTrainPreset: (p: TrainPreset | null) => void
```

Add the import for `TrainPreset` at the top of the file. Find the existing import line (something like):
```typescript
import type { TriagedMail, CalendarItem, Task, ... } from '../api/types'
```
Add `TrainPreset` to that import.

### Step 3: Verify TypeScript compiles

```bash
cd "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend"
npm run build 2>&1 | head -30
```

Expected: no TypeScript errors about `trainPreset`. There may be a TS error in `TrainView.tsx` because it accesses `trainPreset.to` — that's fine, you'll fix it in Task 4.

### Step 4: Commit

```bash
git add "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend/src/api/types.ts"
git add "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend/src/store/useStore.ts"
git commit -m "feat(train): extend TrainPreset type with from/to IDs and when"
```

---

## Task 3: Frontend — parse [TRAIN_NAV] in PhilPanel.tsx

**Files:**
- Modify: `Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend/src/components/Phil/PhilPanel.tsx`

### Step 1: Read the file first

Read `PhilPanel.tsx` and find the `send()` function. Locate the `finally` block (around line 401). It looks like:
```typescript
    } finally {
      setStreaming(false)
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (!last || last.role !== 'phil') return prev
        const updated = [...prev]
        if (last.text === '') {
          updated[updated.length - 1] = { role: 'phil', text: 'Keine Antwort erhalten.', messageId: msgId }
        } else {
          updated[updated.length - 1] = { ...last, messageId: msgId }
        }
        return updated
      })
      // Refresh memory count badge after each chat
      api.memoryStats()
        .then((s) => useStore.getState().setMemoryCount(s.total))
        .catch(() => {})
    }
```

### Step 2: Add TRAIN_NAV parsing to the finally block

Find the `finally` block. The variable `philText` accumulates all streamed text throughout the `send()` function — it's already accessible here. Add the TRAIN_NAV parsing right after `setStreaming(false)`:

Replace:
```typescript
    } finally {
      setStreaming(false)
      setMessages((prev) => {
```

With:
```typescript
    } finally {
      setStreaming(false)

      // Parse [TRAIN_NAV:{...}] token — navigate to TrainView if present
      const navMatch = philText.match(/\[TRAIN_NAV:(\{[\s\S]*?\})\]/)
      if (navMatch) {
        try {
          const preset = JSON.parse(navMatch[1])
          useStore.getState().setTrainPreset(preset)
          useStore.getState().setView('train')
        } catch {
          // malformed token — ignore
        }
      }
      // Strip token from displayed text before rendering
      const cleanText = philText.replace(/\[TRAIN_NAV:\{[\s\S]*?\}\]/g, '').trim()
      if (cleanText !== philText) {
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last && last.role === 'phil') {
            updated[updated.length - 1] = { ...last, text: cleanText }
          }
          return updated
        })
      }

      setMessages((prev) => {
```

### Step 3: Check the import

Make sure `TrainPreset` is not needed here directly — `useStore.getState().setTrainPreset(preset)` passes a plain object that TypeScript will check against the store's type. No extra import needed.

### Step 4: Verify TypeScript compiles

```bash
cd "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend"
npm run build 2>&1 | head -30
```

Expected: no TypeScript errors in PhilPanel.tsx.

### Step 5: Commit

```bash
git add "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend/src/components/Phil/PhilPanel.tsx"
git commit -m "feat(train): parse [TRAIN_NAV] token in PhilPanel, navigate to TrainView"
```

---

## Task 4: Frontend — TrainView auto-search with full preset

**Files:**
- Modify: `Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend/src/components/Views/TrainView.tsx`

### Step 1: Read the existing useEffect

Open `TrainView.tsx`. Find the existing `useEffect` (around line 39):
```typescript
  // Apply preset from Phil (calendar event location)
  useEffect(() => {
    if (trainPreset) {
      setToQuery(trainPreset.to)
      setTrainPreset(null)
      // Auto-search station name
      api.trainStations(trainPreset.to).then(({ stations }) => {
        if (stations.length > 0) { setToStation(stations[0]); setToQuery(stations[0].name) }
      }).catch(() => {})
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
```

### Step 2: Replace with extended useEffect

Replace the entire useEffect above with:
```typescript
  // Apply preset from Phil (chat NAV token or calendar event location)
  useEffect(() => {
    if (!trainPreset) return

    // Full preset from chat: has from_id + to_id — fill all fields and auto-search
    if ('from_id' in trainPreset && trainPreset.from_id && trainPreset.to_id) {
      setFromStation({ id: trainPreset.from_id, name: trainPreset.from_name })
      setFromQuery(trainPreset.from_name)
      setToStation({ id: trainPreset.to_id, name: trainPreset.to_name })
      setToQuery(trainPreset.to_name)
      if (trainPreset.when) {
        // datetime-local input expects "YYYY-MM-DDTHH:MM"
        setDeparture(trainPreset.when.slice(0, 16))
      }
      setTrainPreset(null)
      // Auto-trigger search after state is set (next tick)
      setTimeout(() => { void search() }, 0)
      return
    }

    // Legacy preset from calendar event: only has "to" string
    if ('to' in trainPreset && trainPreset.to) {
      setToQuery(trainPreset.to)
      setTrainPreset(null)
      api.trainStations(trainPreset.to).then(({ stations }) => {
        if (stations.length > 0) { setToStation(stations[0]); setToQuery(stations[0].name) }
      }).catch(() => {})
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
```

**Important:** The `search()` function is defined inside the component after the useEffect — calling it via `setTimeout(() => { void search() }, 0)` defers to the next tick, after state updates from `setFromStation` etc. have been applied. This is necessary because `search()` reads `fromStation` and `toStation` from component state at call time.

But wait — `search()` reads `fromStation` and `toStation` from component-local `useState`. The `setFromStation` call schedules a state update, but the state won't be updated yet when `setTimeout` fires (React batches but setState is async).

**Fix:** Instead of calling `search()` directly, trigger search by calling the HAFAS API directly with the known IDs:

Replace the `setTimeout` line with:
```typescript
      setTrainPreset(null)
      // Directly call HAFAS with known IDs — bypass the search() state dependency
      setLoading(true)
      setError(null)
      const when = trainPreset.when ? new Date(trainPreset.when).toISOString() : undefined
      api.trainJourneys(trainPreset.from_id, trainPreset.to_id, when)
        .then(({ journeys: results }) => {
          setJourneys(results)
          if (results.length === 0) setError('Keine Verbindungen gefunden.')
        })
        .catch((e: unknown) => {
          const msg = e instanceof Error ? e.message : 'Verbindungsfehler'
          setError(`API nicht erreichbar: ${msg}`)
        })
        .finally(() => setLoading(false))
      return
```

The full updated useEffect becomes:
```typescript
  // Apply preset from Phil (chat NAV token or calendar event location)
  useEffect(() => {
    if (!trainPreset) return

    // Full preset from chat: has from_id + to_id — fill all fields and directly search
    if ('from_id' in trainPreset && trainPreset.from_id && trainPreset.to_id) {
      setFromStation({ id: trainPreset.from_id, name: trainPreset.from_name })
      setFromQuery(trainPreset.from_name)
      setToStation({ id: trainPreset.to_id, name: trainPreset.to_name })
      setToQuery(trainPreset.to_name)
      if (trainPreset.when) {
        setDeparture(trainPreset.when.slice(0, 16))
      }
      setTrainPreset(null)
      // Directly call HAFAS with known IDs (bypasses state-async issue)
      setLoading(true)
      setError(null)
      const when = trainPreset.when ? new Date(trainPreset.when).toISOString() : undefined
      api.trainJourneys(trainPreset.from_id, trainPreset.to_id, when)
        .then(({ journeys: results }) => {
          setJourneys(results)
          if (results.length === 0) setError('Keine Verbindungen gefunden.')
        })
        .catch((e: unknown) => {
          const msg = e instanceof Error ? e.message : 'Verbindungsfehler'
          setError(`API nicht erreichbar: ${msg}`)
        })
        .finally(() => setLoading(false))
      return
    }

    // Legacy preset from calendar event: only has "to" string
    if ('to' in trainPreset && trainPreset.to) {
      setToQuery((trainPreset as { to: string }).to)
      setTrainPreset(null)
      api.trainStations((trainPreset as { to: string }).to).then(({ stations }) => {
        if (stations.length > 0) { setToStation(stations[0]); setToQuery(stations[0].name) }
      }).catch(() => {})
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
```

### Step 3: Check the api client has trainJourneys

Open `frontend/src/api/client.ts` and verify `trainJourneys` is defined. It should be something like:
```typescript
trainJourneys: (fromId: string, toId: string, when?: string) =>
  get<{ journeys: TrainJourney[] }>(`/api/trains/journeys?from_id=${fromId}&to_id=${toId}${when ? `&when=${when}` : ''}`)
```
If `when` is not included as optional parameter, add it now.

### Step 4: Verify TypeScript compiles

```bash
cd "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend"
npm run build 2>&1 | head -30
```

Expected: zero TypeScript errors.

### Step 5: Commit

```bash
git add "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend/src/components/Views/TrainView.tsx"
git commit -m "feat(train): TrainView auto-search from full chat preset (from/to/when)"
```

---

## Task 5: End-to-end test

**No automated test file for this** (integration requires live LLM + HAFAS). Manual verification:

### Step 1: Start both servers

Terminal 1:
```bash
cd "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp"
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

Terminal 2:
```bash
cd "Knowledge Navigator Use Cases/UC2_Nachrichten_Triage/webapp/frontend"
npm run dev
```

### Step 2: Open app and send a train query

Open `http://localhost:5173` in the browser. Log in. Open the Phil panel. Type:

> "Welche Züge fahren morgen früh von München nach Frankfurt? Ich muss um 14 Uhr dort sein."

**Expected behavior:**
1. Phil streams a short German acknowledgment (e.g. "Ich habe Verbindungen gefunden und öffne die Reiseplanung für dich.")
2. The `[TRAIN_NAV:{...}]` token does NOT appear in the displayed text
3. After the response completes, the view switches to "Reiseplanung"
4. TrainView shows "München Hbf" and "Frankfurt Hbf" prefilled
5. Results appear automatically (loading spinner, then journey cards)

### Step 3: Test the default fallback

Type: "Wann fährt der nächste Zug nach Berlin?"

**Expected:**
- Phil uses "Nürnberg Hbf" as departure (default)
- TrainView opens with Nürnberg → Berlin and results

### Step 4: Test non-train query (no false trigger)

Type: "Fasse meine letzten E-Mails zusammen"

**Expected:** Phil responds normally, stays in current view, no navigation to TrainView.

### Step 5: Test HAFAS error handling

Stop the backend HAFAS endpoint by temporarily setting a wrong profile, or send a query with a non-existent station: "Zug nach Xyzxyzxyz"

**Expected:** Phil responds normally in chat, no navigation (no `[TRAIN_NAV]` token generated), no crash.

### Step 6: Final commit

```bash
git add -A
git commit -m "feat(train): DB chat integration complete — HAFAS via chat, auto-navigate TrainView"
```

---

## Files changed summary

| File | What changes |
|------|-------------|
| `backend/llm_client.py` | Add `"train_extract"` to `TaskKind` literal and `_LOCAL_TASKS` |
| `backend/main.py` | Add `TRAIN_TRIGGER_RE`, `_extract_train_params()`, `_build_train_nav()`, inject in `chat()` |
| `frontend/src/api/types.ts` | Add `TrainPreset` interface |
| `frontend/src/store/useStore.ts` | Update `trainPreset` type from `{to:string}` to `TrainPreset` |
| `frontend/src/components/Phil/PhilPanel.tsx` | Parse `[TRAIN_NAV]` token in `finally`, strip from display, navigate |
| `frontend/src/components/Views/TrainView.tsx` | Extended `useEffect` — handle full preset + direct HAFAS call |

## Known limitations (by design)

- HAFAS provides **no prices** — the bahn.de link in TrainView remains for booking
- If the LLM misunderstands the route (e.g. city name ambiguity), the user can correct it in TrainView
- The `[TRAIN_NAV]` approach depends on the LLM including the token verbatim — occasionally a very creative model may rephrase it; the regex `\[TRAIN_NAV:(\{[\s\S]*?\})\]` is robust to surrounding whitespace
