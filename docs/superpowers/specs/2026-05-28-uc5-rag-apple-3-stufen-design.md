# UC5 — RAG über `de.wikipedia.org/wiki/Apple` in drei Ausbaustufen (UE1/UE2/UE3)

**Datum:** 2026-05-28
**Status:** Approved by user, implementation started with UE1

## Ziel

Ein dreistufiges RAG-System, das Fragen über den deutschen Wikipedia-Artikel zu *Apple* beantwortet. Lehr-Fokus: dieselbe Quelle, dieselbe Frage, drei Retrieval-Strategien — sichtbar nebeneinander.

- **UE1 — Simple RAG:** klassisches Chunk + Embedding + Top-k.
- **UE2 — RAG + PageIndex:** baumbasiertes Retrieval nach [Vectify PageIndex](https://github.com/VectifyAI/PageIndex).
- **UE3 — RAG + PageIndex + GraphRAG:** [Microsoft GraphRAG](https://github.com/microsoft/graphrag) mit Entity-/Community-Summaries, optional vorgefiltert durch den PageIndex-Subbaum.

## Architektur (Ansatz A — Strategy-Pattern)

Ein FastAPI-Backend mit drei pluggable Retrieval-Strategien, ein React-Frontend mit Tab-Toggle für UE1/UE2/UE3 plus Side-by-Side-Compare. Gemeinsame Datenschicht: Postgres + pgvector + Neo4j (nur UE3).

## Repo-Layout

Neuer Top-Level-Ordner `Knowledge Navigator Use Cases/UC5_RAG_Apple/` mit:

```
backend/   data/  llm/  retrieval/  ingest/  api/   (sechs klar getrennte Schichten)
frontend/  React + Vite + TypeScript + Tailwind + shadcn/ui
data/      snapshots/ + migrations/
tests/     unit/ + integration/
docker-compose.yml + docker-compose.local.yml + Dockerfile + .env.example
```

Strategien kennen nur das `Chunk`-Interface und die DB-Repos. Finale Antwort generiert `llm.generate(query, chunks)` zentral.

## Datenschicht

**Postgres-Schemata:**

- `raw.wikipedia_snapshot` — unveränderter MediaWiki-API-Pull mit `etag`, `revision_id`, `content_hash`.
- `clean.document`, `clean.section` — normalisierter Markdown-Text mit Sektionsbaum (parent_id, level, path).
- `ue1.chunk` — section-aware Chunks ~400 Token, 50 Overlap, `embedding vector(768)`, HNSW-Index.
- `ue2.tree_node` — Vectify-Baum, optional Embeddings auf Summaries.
- `ue3.entity_summary`, `ue3.community_summary` — GraphRAG-Vektorseite (Graph in Neo4j).
- `meta.ingest_run` — Lauf-Historie und Stats pro Strategie und Snapshot.

**Neo4j (nur UE3):** `(:Entity)`, `(:Chunk)`, `(:Community)`, `(:Document)` mit `:MENTIONS`, `:RELATED_TO`, `:IN_COMMUNITY`, `:PART_OF`.

Migrationen via alembic (Postgres) und nummerierte Cypher-Dateien (Neo4j). Re-Ingest ist idempotent pro UE und scoped auf den jeweiligen Snapshot.

## Retrieval-Strategien

Gemeinsames Protocol:

```python
class RetrievalStrategy(Protocol):
    name: str
    def retrieve(self, query: str, k: int = 8) -> RetrievalResult: ...

@dataclass
class RetrievalResult:
    chunks: list[Chunk]
    sources: list[SourceRef]
    trace: dict   # didaktisch sichtbar im Frontend
```

- **UE1:** Query-Embedding → pgvector HNSW Top-k. Optional Cross-Encoder-Rerank (default aus).
- **UE2:** Zweistufig — LLM navigiert Vectify-Baum mit Knoten-Summaries (max. 3 Ebenen, max. 4 Knoten gleichzeitig), Leaf-Texte werden als Chunks zurückgegeben.
- **UE3:** Drei Modi (`local`, `global`, `hybrid` — Default), plus optionaler PageIndex-Subbaum-Vorfilter aus UE2. Community Detection mit Leiden via `graspologic`.

Kostendeckel pro Strategie konfigurierbar: `max_llm_calls_per_query`, `max_tokens_per_call`.

## API (FastAPI)

```
GET  /api/health           DB/LLM-Status
GET  /api/strategies       Verfügbarkeit + letzter Ingest-Lauf pro UE
GET  /api/snapshot         aktueller raw-Snapshot
POST /api/ingest           {strategy, force?} → 202 + run_id (async)
GET  /api/ingest/{run_id}  Lauf-Status
POST /api/query            {query, strategy, k?, mode?, llm: "gemini"|"local"} → SSE-Stream
POST /api/compare          drei Strategien parallel → multiplexed SSE
```

## Frontend (React + Vite + TS)

- **Chat-Tab** (Default): Strategy-Toggle, Modell-Toggle, Streaming-Antwort, Sources-Panel rechts mit Trace-JSON.
- **Compare-Tab**: Eine Eingabe, drei Spalten UE1/UE2/UE3 parallel.
- **Admin-Tab**: Snapshot anzeigen + Re-Fetch, Ingest-Status + Re-Ingest pro UE, Lauf-Historie.

UI: shadcn/ui + Tailwind, Markdown-Rendering, syntax-highlighted Trace.

## LLM und Embeddings

Provider-Abstraktion (`backend/llm/base.py`): `ChatLLM`, `EmbeddingLLM` Protokolle. Zwei Implementierungen:

- **Gemini** (API) — Chat `gemini-2.5-flash`, Embeddings `text-embedding-004` (768 Dim).
- **LM Studio** (lokal) — OpenAI-kompatibel, Modell konfigurierbar (Default `google/gemma-3-12b`).

**Embeddings laufen immer über Gemini**, um die Vektor-Dimension in der DB konsistent zu halten. Nur Chat ist per Request umschaltbar.

## Wikipedia-Loader

MediaWiki-API (`action=parse&page=Apple&prop=text|sections|revid`) statt HTML-Scraping. HTML→Markdown via `markdownify`. `User-Agent`-Header laut Wikipedia-Policy. ETag-basiertes Conditional-Fetch — keine neue Snapshot-Row wenn unverändert.

## Deployment

Ein `docker-compose.yml` mit Traefik-Labels für HTTPS auf einer Subdomain (z.B. `rag-apple.butscher.cloud`). Services: `backend`, `frontend` (statisch via Backend gemountet, UC2-Muster), `postgres` (mit `pgvector`-Image), `neo4j`. `docker-compose.local.yml` ohne Traefik fürs Entwickeln.

## Tests

- Unit: Loader, Chunker, Embedder-Mock, Retrieval-Strategien (Fixture-DB).
- Integration: Ingest+Query End-to-End gegen eine Test-Postgres (testcontainers).
- Manueller Akzeptanztest: drei vorgefertigte Fragen, alle drei UEs, Trace und Antwort vergleichen.

## Nicht im MVP

- Hybrider Embedding-Provider (BGE-M3 lokal) — Folge-Iteration, falls DSGVO/Offline gefordert.
- Cross-Encoder-Rerank — als Plug-in vorbereitet, Default aus.
- Authentifizierung — Demo-Setup, geschützt nur über Traefik-Basic-Auth wenn nötig.
