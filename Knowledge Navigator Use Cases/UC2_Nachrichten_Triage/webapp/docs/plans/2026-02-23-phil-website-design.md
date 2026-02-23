# Phil – Project Website Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan.

**Goal:** A bilingual (EN primary, DE annotations) project website for Phil — a student reimagining of Apple's 1987 Knowledge Navigator concept — hosted on GitHub Pages in its own repository `phil-website`.

**Architecture:** A static landing page (`index.html`) combined with MkDocs Material for the technical documentation, both served from the same GitHub Pages deployment. The landing page functions as a marketing/narrative entry point; MkDocs covers the full technical reference.

**Audience:** Students with Python fundamentals (no Docker required). The site should inspire them to rebuild Phil and understand where the idea comes from.

**Tone:** Humble and appreciative. Phil stands on the shoulders of giants — Otlet, Bush, Licklider, Engelbart, Kay, Sculley. The website honours this intellectual lineage before presenting what we built.

---

## Repository

**Name:** `swrobuts/phil-website`
**Hosting:** GitHub Pages (`swrobuts.github.io/phil-website`)
**Deploy:** GitHub Actions workflow — on push to `main`, runs `mkdocs build` and deploys `/site` + `index.html` to `gh-pages` branch.

```
phil-website/
├── index.html                  ← Landing page (static, self-contained)
├── assets/
│   ├── style.css               ← Landing page styles
│   ├── phil-logo.png           ← Phil avatar / logo
│   ├── apple-kn-thumbnail.jpg  ← Apple KN video thumbnail
│   └── screenshots/            ← Phil dashboard screenshots (5–8 images)
├── docs/                       ← MkDocs source
│   ├── index.md                ← MkDocs home
│   ├── story.md                ← Full lineage & history
│   ├── use-cases.md            ← All 8 Apple UCs vs. Phil 2026
│   ├── features/
│   │   ├── index.md            ← Features overview
│   │   ├── mail-triage.md
│   │   ├── dashboard.md
│   │   ├── calendar.md
│   │   ├── meeting-prep.md
│   │   ├── memory-learning.md
│   │   └── rag-search.md
│   ├── setup.md                ← Local setup guide (uvicorn + npm)
│   ├── architecture.md         ← System overview & data flow
│   ├── tech-stack.md           ← All libraries & services
│   ├── prompts.md              ← CO-STAR prompts
│   └── contributing.md
├── mkdocs.yml
└── .github/
    └── workflows/
        └── deploy.yml
```

---

## Landing Page — Section by Section

The landing page tells a story in seven acts. Each section flows into the next without jarring transitions. The visual language is clean, typographic-first, with restrained use of colour (dark background, warm accent).

### Hero

**Headline:** `Phil — Standing on the Shoulders of Giants`
**Subline:** `Apple imagined a personal knowledge assistant in 1987. Decades of visionary thinking made it possible. In 2026, we rebuilt it.`
**CTA buttons:** [Explore the Story] → scrolls to Lineage · [Get Started] → links to setup.md · [GitHub →] → phil-knowledge-navigator repo

The hero intentionally does *not* claim "we built what Apple couldn't." It frames Phil as a continuation, not a conquest.

---

### Section 1 — The Lineage

*"Every idea has ancestors."*

A horizontal timeline (scrollable on mobile) tracing the intellectual DNA of the Knowledge Navigator from 1935 to 1987, ending with Phil 2026. Each node shows name, year, and one sentence.

| Year | Person / Work | One Sentence |
|------|---------------|--------------|
| 1935 | Paul Otlet · Mundaneum | Envisioned a global network of index cards — an analogue internet. |
| 1937 | H.G. Wells · World Brain | Called for a living world encyclopaedia, continuously updated. |
| 1945 | Vannevar Bush · As We May Think | Described the Memex — a desk that stores and links documents associatively. |
| 1950 | Alan Turing · Computing Machinery and Intelligence | Asked whether machines can think, setting the measure for AI to this day. |
| 1955 | John McCarthy · Dartmouth Conference | Coined the term *Artificial Intelligence* and set its research agenda. |
| 1960 | J.C.R. Licklider · Man-Computer Symbiosis | Envisioned interactive, cooperative partnership between human and machine. |
| 1963 | Ivan Sutherland · Sketchpad | First interactive computer graphics — direct manipulation on screen. |
| 1966 | Joseph Weizenbaum · ELIZA | Built the first chatbot, revealing how readily people attribute empathy to machines. |
| 1968 | Douglas Engelbart · The Mother of All Demos | Showed the mouse, windows, hypertext, and video conferencing — all at once. |
| 1972 | Alan Kay · Dynabook | Designed a portable learning device for children that anticipated tablets by 35 years. |
| 1974 | Ted Nelson · Xanadu | Invented hypertext and imagined a global document network. |
| 1986 | Marvin Minsky · Society of Mind | Described intelligence as the interplay of many simple agents. |
| 1987 | John Sculley / Apple · Knowledge Navigator | United all of this into a concept video — and named the agent **Phil**. |
| **2026** | **Phil (this project)** | **A student reimagining: real code, real AI, same name.** |

**Sculley quote** (displayed large, with attribution):
> *"A future-generation Macintosh might well be a wonderful fantasy machine called the Knowledge Navigator, a discoverer of worlds, a tool as galvanizing as the printing press."*
> — John Sculley, *Odyssey: Pepsi to Apple*, 1987

**Note:** *The assistant in Apple's 1987 video was already called "Phil." We kept the name — as a hat-tip, not a coincidence.*

Source credit line: Dubberly, H. (2024): *Making Knowledge Navigator* · Sculley, J., Byrne, J. A. (1987): *Odyssey: Pepsi to Apple*

---

### Section 2 — The 1987 Vision

*"What Apple showed was fiction. The technology didn't exist."*

- Embedded YouTube thumbnail (linked, not autoplay): Apple Knowledge Navigator concept video (1987)
- 8 use cases Apple demonstrated (from the PPT, Folie 9):
  1. Conversational AI Agent ("Bowtie Avatar" — natural language)
  2. Calendar management & reminders
  3. Video conferencing with a colleague for real-time data exchange
  4. Knowledge research in scientific databases
  5. Data visualisation — dynamic, interactive charts & simulations
  6. Document & message summarisation (briefing)
  7. Simulation of complex scenarios
  8. Multimodal interaction — touch, voice, gestures
- **Sculley's 5 key technologies** (small cards below): Communication infrastructure · 3D real-time animation · Database technologies · Artificial Intelligence · Hypermedia
- Honest framing: *"In 1987, none of the required technology existed. The gap between vision and reality was enormous."*

---

### Section 3 — The Gap (And the Attempt)

*"Apple tried. Honestly."*

A side-by-side comparison: **Vision (Knowledge Navigator)** vs **Reality (Macintosh II, 1987)** — inspired by Folie 10/11 of the PPT.

Then: **Apple Newton (1993)** — the honest attempt that failed.
- Right idea, wrong decade
- Brief, respectful account of why it didn't work (handwriting recognition, price, no connectivity)
- *"The Newton is not a failure story. It is proof that the idea was worth pursuing."*

Technology timeline showing what had to be invented before Phil could exist:
`1990 Speech recognition → 1993 WWW → 2006 Cloud → 2007 Touch (iPhone) → 2010 Tablet (iPad) → 2011 Siri → 2022 ChatGPT`

---

### Section 4 — Phil 2026

*"Today, the technology finally caught up."*

Feature grid — 6 cards, each with icon, title, and 2-sentence description:

| Feature | Description |
|---------|-------------|
| Mail Triage | Phil reads your inbox and categorises messages by priority: VIP / Action Required / FYI / Noise. Powered by Claude. |
| Dashboard | A daily briefing: unread mails, today's calendar, pending tasks — all in one glance. |
| Calendar | Natural-language calendar search. Ask "What's next week?" or "When is the faculty meeting?" |
| Meeting Prep | Given a meeting title, Phil researches participants, pulls related emails, and drafts a briefing. (UC3) |
| Memory & Learning | Phil remembers facts about you across sessions, learns from your feedback via thumbs up/down. |
| RAG Search | Semantic search over your emails and attachments using ChromaDB vector embeddings. |

Screenshots of the actual Phil dashboard below the grid.

---

### Section 5 — How It's Built

Two sub-sections:

**Tech Stack** — badge-style display:
- Backend: FastAPI · Python 3.12 · Anthropic Claude API · ChromaDB · SQLite · RDFlib · pdfplumber · exchangelib
- Frontend: React 18 · TypeScript · Vite · CSS Modules
- Integration: Google Workspace (Gmail + Calendar) · DuckDuckGo Search · PyHafas (Deutsche Bahn)
- Deployment: Docker · Traefik

**CO-STAR Prompt Architecture** — brief explanation of the CO-STAR framework with a collapsed/expandable code block showing the Phil system prompt structure. Links to the full `prompts.md` in MkDocs.

---

### Section 6 — Get Started

Three steps, student-friendly, no Docker required:

```
1. Clone the repo & install dependencies
   git clone https://github.com/swrobuts/phil-knowledge-navigator
   pip install -r backend/requirements.txt
   npm install  (in frontend/)

2. Configure your .env
   Copy backend/.env.example to backend/.env
   Add your Anthropic API key and Google Workspace credentials

3. Run Phil locally
   uvicorn backend.main:app --reload
   npm run dev  (in frontend/)
   → Open http://localhost:5173
```

Links: [Full Setup Guide →] · [.env Reference →] · [Google Auth Setup →]

---

### Section 7 — Footer

- Link to MkDocs documentation site
- GitHub repository link
- Licence (MIT)
- *"Phil is a student project in the course Datenbasierte Fallstudien at THWS / DHBW. It is not affiliated with Apple Inc."*
- *"Built with Claude Code by Anthropic."*

---

## MkDocs Documentation Structure

**Theme:** Material for MkDocs, dark mode default, accent colour warm amber.

**Navigation:**
```yaml
nav:
  - Home: index.md
  - The Story:
      - Intellectual Lineage: story.md
      - Use Cases 1987 vs 2026: use-cases.md
  - Features:
      - Overview: features/index.md
      - Mail Triage: features/mail-triage.md
      - Dashboard: features/dashboard.md
      - Calendar: features/calendar.md
      - Meeting Preparation: features/meeting-prep.md
      - Memory & Learning: features/memory-learning.md
      - Semantic Search: features/rag-search.md
  - Getting Started: setup.md
  - Architecture: architecture.md
  - Tech Stack: tech-stack.md
  - Prompts (CO-STAR): prompts.md
  - Contributing: contributing.md
```

**Key pages:**

- **story.md** — Full lineage narrative, all 14 pioneers with 2–3 sentences each, pop culture references (Jetsons, HAL 9000, Star Trek), HCI milestones (Sketchpad → Mother of All Demos → Macintosh → HyperCard → Knowledge Navigator). Sources cited throughout (Dubberly 2024, Sculley 1987).

- **use-cases.md** — Table mapping all 8 Apple UCs to 2026 equivalents. Clear distinction: what Phil implements directly vs. what today's tools cover (Zoom for UC5, Perplexity for research, voice assistants for UC6). Honest about what Phil doesn't do.

- **prompts.md** — Every system prompt from Phil, formatted using CO-STAR:
  - **C**ontext: background and situation
  - **O**bjective: what the LLM must do
  - **S**tyle: how to communicate
  - **T**one: register and voice
  - **A**udience: who reads the output
  - **R**esponse format: structure of the answer

  Prompts covered: Main system prompt · Mail triage prompt · Calendar keyword extraction · Meeting preparation · Memory extraction · Web search trigger

- **setup.md** — Prerequisites (Python 3.11+, Node 20+, Anthropic API key, Google Workspace account), step-by-step local setup without Docker, Google OAuth configuration, `.env` reference table, troubleshooting section.

- **architecture.md** — System diagram (Mermaid), data flow description, explanation of the hybrid LLM client (cloud vs. local fallback), ChromaDB + SQLite memory architecture, RDF ontology store.

---

## GitHub Actions Deploy

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install mkdocs-material
      - run: mkdocs build          # outputs to /site
      - run: cp index.html site/   # landing page at root
      - run: cp -r assets site/    # landing page assets
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./site
```

The landing page lives at the root of GitHub Pages; MkDocs docs live at `/docs/` (configured via `docs_dir` in `mkdocs.yml`).

---

## Sources & Credits (to appear in site footer and story page)

- Sculley, J., Byrne, J. A. (1987). *Odyssey: Pepsi to Apple*. Harper & Row.
- Dubberly, H. (2024). *Making Knowledge Navigator*. Retrieved 12.01.2026.
- Apple Computer (1987). *Knowledge Navigator* concept video. YouTube.
- Bush, V. (1945). *As We May Think*. The Atlantic.
- Licklider, J.C.R. (1960). *Man-Computer Symbiosis*. IRE Transactions.
- Engelbart, D. (1968). *The Mother of All Demos*. SRI International.
- Kay, A. (1972). *A Personal Computer for Children of All Ages*. Xerox PARC.

---

## Design Notes

- **No triumphalism.** Phil is a tribute, not a boast. Every section that shows what Phil does is preceded by honouring those who made it possible.
- **Honest about limits.** The site clearly states what Phil does *not* do (voice control, video conferencing, real-time simulation) and why.
- **German annotations** for student audience: key terms and setup instructions have DE equivalents in callout boxes.
- **No auto-playing video.** The Apple KN video is thumbnail-linked to YouTube — the user chooses to watch.
- **MIT licence.** The code is open. Students are invited to fork, extend, and improve.
