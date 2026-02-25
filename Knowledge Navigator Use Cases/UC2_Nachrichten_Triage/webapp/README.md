# Phil – Knowledge Navigator

A local AI personal assistant for mail triage, calendar, tasks, and knowledge management.
Inspired by Apple's 1987 Knowledge Navigator concept. Built with FastAPI + React + Claude.

**Full documentation:** [swrobuts.github.io/phil-website](https://swrobuts.github.io/phil-website/)

---

## What Phil does

- **Mail triage** — LLM-powered priority sorting and summarisation of your inbox
- **Calendar** — Google Calendar integration (read + write) via the `gog` CLI
- **Tasks** — Exchange/EWS task sync (THWS, Microsoft 365)
- **Chat** — Streaming conversation with context from your mail, calendar, and knowledge graph
- **RAG / Knowledge graph** — Semantic search over your emails via ChromaDB + RDFlib
- **Memory** — Learns facts from your conversations via SQLite + ChromaDB

---

## Quickest start — Docker Hub (no Python / Node needed)

```bash
# 1. Create backend/.env with your credentials
curl -o .env https://raw.githubusercontent.com/swrobuts/phil-knowledge-navigator/main/backend/.env.example
# Edit .env — fill in ANTHROPIC_API_KEY and GOG_ACCOUNT at minimum

# 2. Pull and run
docker run -d \
  --name phil \
  -p 8000:8000 \
  --env-file .env \
  swrobutsdocker/phil:latest
```

Open **http://localhost:8000** — done.

To stop: `docker stop phil && docker rm phil`
To update: `docker pull swrobutsdocker/phil:latest && docker stop phil && docker rm phil` then re-run.

---

## Prerequisites (dev mode only)

| Tool | Minimum version | Check |
|------|----------------|-------|
| Python | 3.12 | `python3 --version` |
| Node.js | 20 | `node --version` |
| Git | any | `git --version` |
| `gog` CLI | any | `gog version` (see below) |

At least one LLM credential is required (Anthropic API key **or** a running LM Studio instance).

---

## Quick start (dev mode)

```bash
# 1. Clone
git clone https://github.com/swrobuts/phil-knowledge-navigator.git
cd phil-knowledge-navigator

# 2. Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# 3. Frontend dependencies
cd frontend && npm install && cd ..

# 4. Environment file
cp backend/.env.example backend/.env
# Open backend/.env and fill in at least ANTHROPIC_API_KEY and GOG_ACCOUNT
```

Then open **two terminals**:

```bash
# Terminal 1 — backend (port 8001)
uvicorn backend.main:app --reload --port 8001

# Terminal 2 — frontend (port 5173)
cd frontend && npm run dev
```

Open **http://localhost:5173** and log in with your Exchange/IMAP credentials (THWS or Microsoft 365).

---

## Docker (single container, no Python/Node needed)

```bash
cp backend/.env.example backend/.env
# (edit backend/.env)

# Local testing
docker compose -f docker-compose.local.yml up --build
```

Open **http://localhost:8000**.

For production with Traefik/HTTPS: `docker compose up` (see `docker-compose.yml`).

---

## Environment variables

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Required for | Description |
|----------|-------------|-------------|
| `ANTHROPIC_API_KEY` | LLM (cloud) | Claude API key — `sk-ant-...` |
| `OPENAI_API_KEY` | Embeddings + TTS | OpenAI key — `sk-proj-...` |
| `GOG_ACCOUNT` | Google Calendar | Your Gmail address |
| `GOG_KEYRING_PASSWORD` | Docker + Google Cal | OAuth token password (see docs) |
| `LOCAL_LLM_ENDPOINT` | LLM (local) | LM Studio URL, default `http://localhost:1234/v1` |
| `LOCAL_LLM_MODEL` | LLM (local) | Model name in LM Studio |

Exchange/IMAP credentials (THWS, M365) are entered **in the app's login screen**, not in `.env`.

---

## Setting up Google Calendar (`gog`)

Phil uses the [`gog`](https://github.com/nicholasgasior/gog) CLI to read and write Google Calendar events.

```bash
# Install (macOS example)
brew install nicholasgasior/tap/gog
# or download binary from GitHub releases and place in ~/bin/gog

# Authenticate (opens browser for Google OAuth)
gog auth login

# Verify
gog calendar events --account your@gmail.com --max 5
```

After successful auth, set `GOG_ACCOUNT=your@gmail.com` in `backend/.env`.

For Docker: run `gog auth login` on the host, then export the keyring password as `GOG_KEYRING_PASSWORD`.

---

## ChromaDB / knowledge base

Phil stores email embeddings in ChromaDB at `/tmp/phil_chroma`.

**Important:** This path must be on a local disk — not OneDrive, iCloud, Dropbox, or any network drive. Memory-mapped files (mmap) fail on network volumes.

To pre-populate the knowledge base, triage your mails once via the Mail view (the "Analysieren" button). Each triage run indexes the fetched emails.

---

## Project structure

```
webapp/
  backend/        FastAPI app, LLM client, Exchange/IMAP helpers, RAG, memory
  frontend/       React + TypeScript + Vite
  static/         Built frontend (output of npm run build)
  Dockerfile      Two-stage build: Node → Python
  docker-compose.yml           Production (Traefik)
  docker-compose.local.yml     Local testing
  backend/.env.example
```

---

## Licence

MIT. Not affiliated with Apple Inc. Built at THWS as a student project.
