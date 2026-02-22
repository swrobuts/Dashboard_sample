# UC3 Meeting-Vorbereitung Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a calendar event is clicked, Phil proactively suggests creating a meeting briefing (attendees, related mails, last interaction, agenda proposal) delivered as a structured LLM-streamed response.

**Architecture:** New `POST /api/briefing` backend endpoint extracts persons from the event subject, runs RAG search, and streams a structured Markdown briefing via SSE. The PhilPanel shows a prominent banner when a near-future calendar event is selected; clicking it triggers the stream using the same infrastructure as `/api/chat`.

**Tech Stack:** FastAPI + Pydantic (backend), React + TypeScript (frontend), existing `knowledge_store.search()` for RAG, existing SSE streaming pattern from `/api/chat`.

---

## Context for the Implementer

### Project structure
```
webapp/
  backend/
    main.py          ← FastAPI app, all endpoints
    llm_client.py    ← get_llm_client(), HybridLLMClient etc.
    knowledge_store.py ← ChromaDB RAG
  frontend/src/
    api/
      client.ts      ← api.chatStream(), all API calls
      types.ts       ← TypeScript interfaces
    components/Phil/
      PhilPanel.tsx  ← Phil chat panel, quick actions, send()
      PhilPanel.module.css ← all Phil panel styles
```

### Key existing patterns to reuse

**Backend SSE streaming** (from `@app.post("/api/chat")` at line 886 in main.py):
```python
def generate():
    for text in llm.stream(task="chat", prompt=user_msg, max_tokens=1024, system=SYSTEM):
        yield f"data: {text}\n\n"
    yield "data: [DONE]\n\n"
return StreamingResponse(generate(), media_type="text/event-stream")
```

**RAG search** (`_build_rag_context` at line 824 in main.py):
```python
results = knowledge_store.search(query, n_results=5)
# Each result: { date, sender, subject, kategorie, score, summary }
```

**Frontend SSE reading** (from `api.chatStream` at line 138 in client.ts):
```typescript
// POST endpoint, reads SSE lines "data: ...\n\n", closes on "[DONE]"
```

**PhilPanel `send()` function** (line 221 in PhilPanel.tsx) — streams into `messages` state via `setMessages`.

**CSS color tokens** (in `PhilPanel.module.css`):
- `.quickBtnGraph` → purple `#7C3AED`
- `.quickBtnTrain` → red `#DC2626`
- `.quickBtnCalThread` → cyan `#0891B2`
- Briefing should use green `#059669` (not yet used, fits "preparation" semantics)

---

## Task 1: Backend — `BriefingRequest` model + `/api/briefing` endpoint

**Files:**
- Modify: `backend/main.py` — add after line 952 (after the `/api/chat` endpoint's `return StreamingResponse(...)`)

**Step 1: Add the Pydantic model**

Insert after the closing of the `/api/chat` endpoint (after line 952), before the `# ── Graph / Knowledge-Map ──` comment at line 955:

```python
# ── Meeting Briefing (UC3) ────────────────────────────────────────────────────
class BriefingRequest(BaseModel):
    subject: str
    start: str = ""
    end: str = ""
    location: str = ""
    body: str = ""
```

**Step 2: Add the endpoint**

Immediately after the model:

```python
BRIEFING_SYSTEM = """\
Du bist PHIL, der persönliche KI-Assistent von Prof. Dr. Butscher.
Erstelle ein kompaktes Meeting-Briefing auf Deutsch.
Verwende EXAKT diese Markdown-Struktur, keine Abweichungen:

## 👤 Teilnehmer
<Namen aus dem Termin, oder "Keine erkannt">

## 📬 Letzte Mails
<Relevante Mails aus dem Kontext mit Datum, oder "Keine gefunden.">

## 📋 Agenda-Vorschlag
<3–5 konkrete Punkte basierend auf Termin und Mails>

Sei prägnant. Maximal 200 Wörter insgesamt. Kein Einleitungssatz.
"""


@app.post("/api/briefing")
def briefing(req: BriefingRequest, session_id: str | None = Cookie(default=None)):
    """Erstellt ein Meeting-Briefing: Teilnehmer, Mails, Agenda (SSE streaming)."""
    session = _get_session(session_id)
    llm = _get_llm(session)

    # 1. Person aus Betreff extrahieren
    person_match = re.search(
        r'\bmit\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)+)',
        req.subject,
        re.IGNORECASE,
    )
    person_name = person_match.group(1) if person_match else None

    # 2. RAG-Suche nach ähnlichen Mails
    rag_lines: list[str] = []
    rag_query = f"{person_name} {req.subject}" if person_name else req.subject
    if knowledge_store is not None:
        try:
            results = knowledge_store.search(rag_query, n_results=5)
            for r in results:
                if r.get("score", 0) >= 0.60:
                    rag_lines.append(
                        f"  [{r['date']}] Von: {r['sender']} | Betreff: {r['subject']}"
                        f" | Relevanz: {int(r['score'] * 100)}%"
                    )
        except Exception as exc:
            logging.warning(f"[Briefing] RAG fehlgeschlagen: {exc}")

    # 3. Prompt zusammenbauen
    parts = [f"Termin: {req.subject}"]
    if req.start:
        parts.append(f"Datum/Uhrzeit: {req.start[:16].replace('T', ' ')}")
    if req.end:
        parts.append(f"Ende: {req.end[:16].replace('T', ' ')}")
    if req.location:
        parts.append(f"Ort: {req.location}")
    if person_name:
        parts.append(f"Erkannte Person: {person_name}")
    if rag_lines:
        parts.append("\nRelevante frühere Mails:")
        parts.extend(rag_lines)
    else:
        parts.append("\nKeine ähnlichen Mails gefunden.")

    user_prompt = "\n".join(parts)

    def generate():
        stream_kwargs = dict(task="chat", prompt=user_prompt, max_tokens=512, system=BRIEFING_SYSTEM)
        try:
            for text in llm.stream(**stream_kwargs):
                yield f"data: {text}\n\n"
        except Exception as exc:
            logging.warning(f"[Briefing] LLM '{getattr(llm, 'mode', '?')}' fehlgeschlagen: {exc}")
            if getattr(llm, "mode", "cloud") != "cloud":
                try:
                    for text in get_llm_client("cloud").stream(**stream_kwargs):
                        yield f"data: {text}\n\n"
                except Exception as exc2:
                    yield f"data: [Fehler: {type(exc2).__name__}]\n\n"
            else:
                yield f"data: [Fehler: {type(exc).__name__}]\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Step 3: Verify the server starts without syntax errors**

```bash
cd /path/to/webapp
python3 -c "import backend.main; print('OK')"
```
Expected output: `OK` (no tracebacks)

**Step 4: Smoke-test the endpoint manually**

```bash
curl -s -N -X POST http://localhost:8001/api/briefing \
  -H "Content-Type: application/json" \
  -b "session_id=<your-session-cookie>" \
  -d '{"subject": "Austausch mit Kai Hufnagel", "start": "2026-02-24T10:00", "location": "Büro"}'
```
Expected: SSE stream with `data: ` lines containing Markdown, ending with `data: [DONE]`

> **Note:** Get your session cookie by checking the browser DevTools → Application → Cookies → `session_id` after logging in at http://localhost:8001

**Step 5: Commit**

```bash
git add backend/main.py
git commit -m "feat(uc3): POST /api/briefing endpoint — person extraction, RAG, SSE stream"
```

---

## Task 2: Frontend API — `briefingStream()` in client.ts

**Files:**
- Modify: `frontend/src/api/client.ts` — add after the `chatStream` method (after line 176)

**Step 1: Add `briefingStream` to the `api` object**

In `client.ts`, find the `chatStream` method (ends around line 176 with `},`). Add immediately after it, before the closing `}` of the `api` object:

```typescript
  // Meeting Briefing (UC3) — SSE streaming identical to chatStream
  briefingStream: (event: {
    subject: string
    start?: string | null
    end?: string | null
    location?: string | null
    body?: string | null
  }): ReadableStream<string> => {
    const ctrl = new AbortController()
    return new ReadableStream({
      async start(controller) {
        try {
          const r = await fetch('/api/briefing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              subject: event.subject,
              start: event.start ?? '',
              end: event.end ?? '',
              location: event.location ?? '',
              body: event.body ?? '',
            }),
            signal: ctrl.signal,
          })
          if (!r.ok || !r.body) {
            _handle401(r.status)
            controller.error(new Error(`Fehler ${r.status}`))
            return
          }
          const reader = r.body.getReader()
          const dec = new TextDecoder()
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const chunk = dec.decode(value)
            for (const line of chunk.split('\n')) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6)
                if (data === '[DONE]') { controller.close(); return }
                controller.enqueue(data)
              }
            }
          }
          controller.close()
        } catch (e) {
          controller.error(e)
        }
      },
      cancel() { ctrl.abort() },
    })
  },
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend
npm run build 2>&1 | tail -20
```
Expected: Build succeeds, no TypeScript errors mentioning `briefingStream`.

**Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(uc3): api.briefingStream() — SSE client for /api/briefing"
```

---

## Task 3: Frontend — PhilPanel briefing banner (state + render)

**Files:**
- Modify: `frontend/src/components/Phil/PhilPanel.tsx` — add state + banner render
- Modify: `frontend/src/components/Phil/PhilPanel.module.css` — add banner styles

**Step 1: Add `briefingDone` state to PhilPanel**

In `PhilPanel.tsx`, find the existing state declarations (around line 101–108):
```typescript
const [ttsIdx, setTtsIdx] = useState<number | null>(null)
```

Add after the last `useState` (before `const messagesEndRef`):
```typescript
const [briefingDone, setBriefingDone] = useState(false)
```

**Step 2: Reset `briefingDone` when selection changes**

Find the existing `useEffect` that scrolls to bottom (line 119):
```typescript
useEffect(() => {
  messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
}, [messages])
```

Add a NEW `useEffect` after it:
```typescript
// Reset briefing banner when a new item is selected
useEffect(() => {
  setBriefingDone(false)
}, [selection])
```

**Step 3: Compute `showBriefingBanner`**

Find the `linkedinName` constant (around line 180). Add BEFORE it:

```typescript
const showBriefingBanner = (() => {
  if (briefingDone) return false
  if (selection?.type !== 'calendar') return false
  const start = selection.item.start ? new Date(selection.item.start) : null
  if (!start) return false
  const diffDays = (start.getTime() - Date.now()) / (1000 * 60 * 60 * 24)
  return diffDays >= -0.5 && diffDays <= 7
})()
```

**Step 4: Render the briefing banner**

In the JSX, find the `{/* ── Quick Actions ──... */}` div (around line 317). Add the banner as the FIRST child inside `<div className={styles.quickActions}>`, before the `{quickActions.map(...)}`:

```tsx
{showBriefingBanner && (
  <div className={styles.briefingBanner}>
    <span className={styles.briefingBannerLabel}>
      📋 Meeting-Briefing für „{selection!.item.subject.slice(0, 40)}{selection!.item.subject.length > 40 ? '…' : ''}"
    </span>
    <button
      className={styles.briefingBannerBtn}
      onClick={() => sendBriefing()}
      disabled={streaming}
    >
      Vorbereitung erstellen →
    </button>
  </div>
)}
```

> `sendBriefing()` is implemented in Task 4.

**Step 5: Add CSS for the briefing banner**

In `PhilPanel.module.css`, find `.quickBtn` (line 96). Add BEFORE it:

```css
/* ── Briefing Banner (UC3) ─────────────────────────────────────────────── */
.briefingBanner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #ECFDF5;
  border: 1px solid #059669;
  border-radius: 8px;
  margin-bottom: 4px;
}
.briefingBannerLabel {
  flex: 1;
  font-size: var(--text-xs);
  color: #065F46;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.briefingBannerBtn {
  flex-shrink: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  padding: 4px 10px;
  border: 1px solid #059669;
  border-radius: 6px;
  background: #059669;
  color: white;
  cursor: pointer;
  transition: background var(--transition);
  font-family: var(--font);
}
.briefingBannerBtn:hover:not(:disabled) {
  background: #047857;
  border-color: #047857;
}
.briefingBannerBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

**Step 6: Verify the banner renders (visual check)**

```bash
cd frontend && npm run dev
```
Open http://localhost:5173, log in, click a calendar event scheduled within the next 7 days. The green briefing banner should appear above the quick action buttons. The button should be disabled while streaming.

**Step 7: Commit**

```bash
git add frontend/src/components/Phil/PhilPanel.tsx frontend/src/components/Phil/PhilPanel.module.css
git commit -m "feat(uc3): briefing banner in PhilPanel — state, trigger logic, styles"
```

---

## Task 4: Frontend — `sendBriefing()` function wires up the stream

**Files:**
- Modify: `frontend/src/components/Phil/PhilPanel.tsx` — add `sendBriefing()` function

**Step 1: Add `sendBriefing()` to PhilPanel**

Find the existing `send()` function (around line 221 in PhilPanel.tsx). Add the new function BEFORE `send()`:

```typescript
async function sendBriefing() {
  if (!selection || selection.type !== 'calendar' || streaming) return
  setBriefingDone(true)
  setRagResults([])
  setMailGraphData(null)

  const item = selection.item
  setMessages((prev) => [...prev, { role: 'user', text: `📋 Meeting-Briefing für „${item.subject}"` }])
  setStreaming(true)
  stopAudio()

  // RAG: search by event subject to populate the sources block
  api.knowledgeSearch(item.subject, 5)
    .then(({ results }) => setRagResults(results))
    .catch(() => {})

  let philText = ''
  setMessages((prev) => [...prev, { role: 'phil', text: '' }])

  try {
    const stream = api.briefingStream({
      subject: item.subject,
      start: item.start,
      end: item.end,
      location: item.location,
      body: item.body,
    })
    const reader = stream.getReader()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      philText += value
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = { role: 'phil', text: philText }
        return updated
      })
    }
  } catch (e) {
    const errText = e instanceof Error ? e.message : 'Briefing fehlgeschlagen.'
    setMessages((prev) => {
      const updated = [...prev]
      updated[updated.length - 1] = { role: 'phil', text: errText }
      return updated
    })
  } finally {
    setStreaming(false)
    setMessages((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].role === 'phil' && prev[prev.length - 1].text === '') {
        const updated = [...prev]
        updated[updated.length - 1] = { role: 'phil', text: 'Keine Antwort erhalten.' }
        return updated
      }
      return prev
    })
  }
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: Build succeeds, zero errors.

**Step 3: End-to-end test**

1. Make sure the backend server is running on port 8001
2. Open http://localhost:8001 in the browser
3. Log in
4. Go to Calendar view
5. Click on any event that is scheduled within the next 7 days
6. The green briefing banner should appear in the Phil panel
7. Click "Vorbereitung erstellen →"
8. Phil should stream a response with exactly three Markdown sections: `## 👤 Teilnehmer`, `## 📬 Letzte Mails`, `## 📋 Agenda-Vorschlag`
9. The banner should disappear after clicking (since `briefingDone = true`)
10. Clicking a different future event should reset the banner (it appears again)
11. Clicking a past event (> 0.5 days ago) should NOT show the banner

**Step 4: Commit**

```bash
git add frontend/src/components/Phil/PhilPanel.tsx
git commit -m "feat(uc3): sendBriefing() — wires briefing banner to /api/briefing SSE stream"
```

---

## Definition of Done

- [ ] `POST /api/briefing` returns valid SSE stream with Markdown in three sections
- [ ] Green banner appears in PhilPanel when a calendar event ≤ 7 days away is selected
- [ ] Banner disappears after clicking and does not reappear for the same selection
- [ ] Selecting a different event resets the banner
- [ ] Past events (> 0.5 days ago) do not show the banner
- [ ] LLM cloud fallback works if local LLM is unavailable
- [ ] No TypeScript build errors
- [ ] Server starts without errors after changes
