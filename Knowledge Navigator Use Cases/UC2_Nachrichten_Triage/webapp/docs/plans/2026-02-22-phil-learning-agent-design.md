# Phil als lernender Agent — Design

**Datum:** 2026-02-22
**Status:** Genehmigt

---

## Ziel

Phil soll kontinuierlich aus allen verfügbaren Quellen lernen und ein persistentes Weltbild über den Kontext von Prof. Dr. Butscher aufbauen — primär aus Chats, ergänzend aus Mails, Anhängen, Terminen und Aufgaben. Das Wissen wird automatisch verwaltet; der User greift nur zur Kontrolle und Korrektur ein.

---

## Architektur

### Neue Dateien

```
backend/
  memory_store.py       ← MemoryStore: SQLite-Metadaten + ChromaDB-Embeddings
  web_search.py         ← DuckDuckGo Instant-Answer (kein API-Key)

data/
  memory.db             ← SQLite (persistiert auf Disk, nicht OneDrive)
  /tmp/phil_chroma/     ← ChromaDB (bestehend), neue Collection: phil_facts
```

### Geänderte Dateien

```
backend/main.py                          ← Memory-Integration in /api/chat,
                                           neue Endpunkte /api/memory/*
frontend/src/api/client.ts               ← Memory-API-Methoden
frontend/src/components/Phil/PhilPanel.tsx    ← Thumbs up/down an Bubbles
frontend/src/components/Views/MemoryView.tsx  ← NEU: Control Panel
frontend/src/components/Views/MemoryView.module.css
frontend/src/components/Layout/Sidebar.tsx    ← 🧠-Icon + Badge
frontend/src/store/useStore.ts                ← memory-State
```

---

## Datenmodell

### SQLite-Tabelle `facts`

```sql
CREATE TABLE IF NOT EXISTS facts (
    id              TEXT PRIMARY KEY,   -- uuid4
    text            TEXT NOT NULL,      -- "Flaschenpost = Getränkelieferdienst"
    category        TEXT NOT NULL,      -- Person | Projekt | Konzept | Prozedur | Ort
    source          TEXT NOT NULL,      -- chat | mail | calendar | task | web
    source_ref      TEXT,               -- z.B. Mail-Betreff, Terminname
    confidence      REAL DEFAULT 0.7,   -- 0.0–1.0
    positive_votes  INTEGER DEFAULT 0,
    negative_votes  INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,      -- ISO-8601
    corrected_at    TEXT,
    correction_note TEXT
);
```

### RLHF Confidence-Modell

| Quelle   | Startwert |
|----------|-----------|
| chat     | 0.70      |
| mail     | 0.60      |
| calendar | 0.60      |
| task     | 0.60      |
| web      | 0.80      |

**Formel:** `confidence = clamp(base + pos×0.05 − neg×0.10, 0.10, 1.00)`

Fakten mit `confidence < 0.30` werden nicht mehr als Kontext injiziert, bleiben aber im Control Panel sichtbar.

---

## Lernpipeline

### Triggerquellen

| Quelle       | Zeitpunkt                          | Mechanismus                              |
|--------------|------------------------------------|------------------------------------------|
| **Chat**     | Nach jeder Phil-Antwort (async)    | LLM Fact-Extraction-Pass                 |
| **Mails**    | Nach `/api/exchange/fetch`         | Erweiterung der bestehenden entities-Extraktion |
| **Kalender** | Beim Laden via `/api/calendar`     | Regelbasiert (Regex Personenname, Firma) |
| **Aufgaben** | Beim Laden via `/api/tasks`        | Regelbasiert (Titelanalyse)              |
| **Web**      | Explizit im Chat (keyword-trigger) | DuckDuckGo → Snippets → Fakten           |

### Chat Fact-Extraction (Kernmechanismus)

Nach jeder gestreamten Phil-Antwort läuft **async/non-blocking** ein LLM-Call:

```
System:
  "Extrahiere aus diesem Gespräch maximal 3 neue Fakten über Personen,
   Projekte, Konzepte oder Abläufe. Nur konkrete, neue Informationen.
   Format: JSON [{\"text\": \"...\", \"category\": \"...\", \"confidence\": 0.7}]
   Kategorien: Person | Projekt | Konzept | Prozedur | Ort
   Wenn keine neuen Fakten: []"

Input: [User-Nachricht] + [Phil-Antwort]
```

→ `MemoryStore.upsert_facts()` — Duplikate via Embedding-Similarity (threshold 0.92) erkannt und gemergt.

### Kontext-Injektion im Chat

```
=== PHIL'S GEDÄCHTNIS (gespeicherte Fakten) ===
  [Person]    Max Müller = Kooperationspartner HM  (Konfidenz: 85%)
  [Konzept]   Flaschenpost = Getränkelieferdienst  (Konfidenz: 90%)
  [Prozedur]  Praxis Dr. Huber: immer nüchtern kommen  (Konfidenz: 70%)
```

- Maximal 10 semantisch relevanteste Fakten zur aktuellen Frage
- Keine Fakten unter 30% Konfidenz
- Injiziert nach dem bestehenden RAG- und Ontologie-Block

### Web-Suche

**Trigger:** Regex im Chat-Message:
```python
re.search(r'recherchiere|suche mal|was ist|wer ist|was bedeutet', msg, re.IGNORECASE)
```

**Ablauf:** DuckDuckGo Instant-Answer-API → Top-3-Snippets → in Chat-Kontext injiziert → als Fakten mit `source=web` gespeichert.

---

## API-Endpunkte

| Method | Path | Beschreibung |
|--------|------|--------------|
| `GET` | `/api/memory/facts` | Alle Fakten (Query-Params: `category`, `min_confidence`) |
| `DELETE` | `/api/memory/facts/{id}` | Fakt löschen |
| `PATCH` | `/api/memory/facts/{id}` | Fakt korrigieren (`text`, `correction_note`) |
| `POST` | `/api/memory/feedback` | `{ fact_id, rating: "up"\|"down" }` |
| `GET` | `/api/memory/stats` | Anzahl pro Kategorie + Konfidenz-Verteilung |

---

## Frontend

### Thumbs up/down an Phil-Bubbles (`PhilPanel.tsx`)

- Jede Phil-Nachricht bekommt nach dem Streamen `[👍] [👎]`
- Klick → `POST /api/memory/feedback`
- Nach Klick: Icon ausgefüllt, Wiederklick nicht möglich
- Nicht angezeigt bei Nachrichten ohne extrahierte Fakten (z.B. reine Begrüßungen)
- Message-Objekt erhält optionales Feld `fact_ids: string[]`

### Memory Control Panel (`MemoryView.tsx`)

- Neuer Sidebar-Tab mit 🧠-Icon + Badge (Fakt-Gesamtanzahl)
- Tabelle: **Fakt** | **Kategorie** | **Quelle** | **Konfidenz** (Farbbalken) | **Aktionen** (✏ / 🗑)
- Filter: Kategorie-Chips + Min-Konfidenz-Slider
- Kein "Hinzufügen"-Button — reine Kontroll- und Korrektursicht
- Live-Update nach jedem Chat (polling oder nach Response-Ende)

---

## Fehlerbehandlung

| Fehlerfall | Verhalten |
|------------|-----------|
| Fact-Extraction schlägt fehl | Silent fail — kein Impact auf Chat |
| ChromaDB nicht erreichbar | Fallback auf SQLite LIKE-Query für Retrieval |
| Web-Suche schlägt fehl | Chat-Hinweis „Suche gerade nicht verfügbar", kein Crash |
| SQLite locked | WAL-Mode, serialisierte Writes |
| Memory-Block zu groß | Hard-Limit: 10 Fakten, max. 800 Tokens |

---

## Bewusste Einschränkungen (YAGNI)

- Kein Export/Import von Fakten
- Kein Multi-User-Memory
- Kein automatischer Web-Crawl ohne User-Trigger
- Keine Fakt-Versionierung (nur `corrected_at` + `correction_note`)

---

## Testbarkeit

- `MemoryStore` mit In-Memory-SQLite (`":memory:"`) und Mock-ChromaDB unit-testbar
- Fact-Extraction mit fixture-basierten Chat-Paaren testbar
- Feedback-Endpoint mit konfigurierbarer Konfidenz-Startbasis testbar
- Web-Search mit `httpx.MockTransport` mockbar
