# UC5 — RAG über `de.wikipedia.org/wiki/Apple` in drei Stufen

Dreistufiges RAG-System zur Beantwortung von Fragen über den deutschen
Wikipedia-Artikel zu *Apple*:

- **UE1 — Simple RAG** (Chunk + Embedding + Top-k)
- **UE2 — + PageIndex** (Vectify, baumbasiertes Retrieval)
- **UE3 — + GraphRAG** (Microsoft GraphRAG, Entity-/Community-Summaries)

LLMs: Google Gemini (API) und LM Studio + Gemma 3 (lokal).
Daten: Postgres + pgvector (alle UEs) und Neo4j (nur UE3).
Frontend: React + Vite + TS, Tab-Toggle für die drei Stufen plus Compare-Ansicht.

Spec: [`../../docs/superpowers/specs/2026-05-28-uc5-rag-apple-3-stufen-design.md`](../../docs/superpowers/specs/2026-05-28-uc5-rag-apple-3-stufen-design.md)

## Lokal entwickeln (UE1)

```bash
cp .env.example .env
# Trage GEMINI_API_KEY ein. Local-LLM-URL/Modell bei Bedarf anpassen.

# Variante A — alles via Docker Compose
docker compose -f docker-compose.local.yml up --build
# → Backend: http://localhost:8000/api/health
# → Postgres: localhost:5432

# Variante B — Postgres im Container, Backend im venv
docker compose -f docker-compose.local.yml up -d db
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
export PYTHONPATH=$(pwd)
uvicorn backend.main:app --reload --port 8000
```

Status der Implementation: Scaffolding + `/api/health`. Migrationen, Ingest und
Frontend folgen in den nächsten Schritten — siehe Spec.
