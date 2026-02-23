# Phil Website Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `swrobuts/phil-website` — a bilingual GitHub Pages site with a narrative landing page and MkDocs technical documentation honouring the intellectual lineage of the Knowledge Navigator.

**Architecture:** Static `index.html` landing page + MkDocs Material docs site, both deployed from one repo via GitHub Actions. Landing page lives at the root, MkDocs at `/`. The GitHub Actions workflow builds MkDocs into `/site`, copies `index.html` + `assets/` there, then deploys to `gh-pages` branch.

**Tech Stack:** HTML5 · CSS3 (custom, no framework) · MkDocs Material · GitHub Actions · GitHub Pages

**Design reference:** `docs/plans/2026-02-23-phil-website-design.md` in the `phil-knowledge-navigator` repo

---

## Prerequisites (do these before Task 1)

1. Create repo `swrobuts/phil-website` on GitHub (public, no auto-init)
2. Clone locally: `git clone https://github.com/swrobuts/phil-website.git && cd phil-website`
3. Install MkDocs Material: `pip install mkdocs-material`
4. Enable GitHub Pages in repo settings → Source: `gh-pages` branch

---

## Task 1: Repo scaffold — mkdocs.yml + deploy workflow

**Files:**
- Create: `mkdocs.yml`
- Create: `.github/workflows/deploy.yml`
- Create: `docs/index.md` (placeholder)

**Step 1: Create `mkdocs.yml`**

```yaml
site_name: Phil – Knowledge Navigator
site_url: https://swrobuts.github.io/phil-website/
site_description: A student reimagining of Apple's 1987 Knowledge Navigator
site_author: Robert Butscher

docs_dir: docs
site_dir: site

theme:
  name: material
  language: en
  palette:
    scheme: slate
    primary: amber
    accent: amber
  font:
    text: DM Sans
    code: DM Mono
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.top
    - search.highlight
    - content.code.copy

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

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.superfences
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.tabbed:
      alternate_style: true
  - attr_list
  - md_in_html
  - tables

extra:
  social:
    - icon: fontawesome/brands/github
      link: https://github.com/swrobuts/phil-knowledge-navigator

copyright: >
  Phil is a student project at THWS / DHBW. Not affiliated with Apple Inc.
  Built with Claude Code by Anthropic. MIT Licence.
```

**Step 2: Create `.github/workflows/deploy.yml`**

```yaml
name: Deploy Phil Website

on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install MkDocs Material
        run: pip install mkdocs-material

      - name: Build MkDocs
        run: mkdocs build

      - name: Copy landing page into site root
        run: |
          cp index.html site/
          cp -r assets site/

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./site
```

**Step 3: Create `docs/index.md`**

```markdown
# Phil — Knowledge Navigator

Welcome to the Phil documentation. For the full story, start with [The Intellectual Lineage](story.md).

Phil is a working reimagination of Apple's 1987 Knowledge Navigator — a personal AI assistant
that manages email, calendar, tasks, and knowledge, built with today's AI tools.

> The agent in Apple's 1987 concept video was already called "Phil."
> We kept the name — as a hat-tip, not a coincidence.

## Quick Links

- [The Story](story.md) — Where the idea came from
- [Getting Started](setup.md) — Run Phil locally in minutes
- [Prompts (CO-STAR)](prompts.md) — The prompt engineering behind Phil
- [GitHub Repository](https://github.com/swrobuts/phil-knowledge-navigator)
```

**Step 4: Verify MkDocs builds**

```bash
mkdocs build
# Expected: INFO - Documentation built successfully
# Expected: site/ directory created
```

**Step 5: Initial commit**

```bash
git add mkdocs.yml .github/workflows/deploy.yml docs/index.md
git commit -m "feat: repo scaffold — mkdocs.yml, deploy workflow, docs home"
git push origin main
```

---

## Task 2: Landing page — HTML skeleton + CSS

**Files:**
- Create: `index.html`
- Create: `assets/style.css`

**Step 1: Create `assets/style.css`**

```css
/* ── Reset & tokens ─────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #0d1117;
  --surface:   #161b22;
  --border:    #30363d;
  --accent:    #f0a500;
  --accent-dim:#c68a00;
  --text:      #e6edf3;
  --muted:     #8b949e;
  --font-sans: 'DM Sans', system-ui, sans-serif;
  --font-mono: 'DM Mono', monospace;
  --radius:    8px;
  --max-w:     1100px;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  line-height: 1.6;
}

/* ── Typography ─────────────────────────────────────────────── */
h1 { font-size: clamp(2rem, 5vw, 3.5rem); font-weight: 700; line-height: 1.1; }
h2 { font-size: clamp(1.4rem, 3vw, 2rem); font-weight: 600; }
h3 { font-size: 1.1rem; font-weight: 600; }
p  { color: var(--muted); max-width: 65ch; }

/* ── Layout helpers ─────────────────────────────────────────── */
.container { max-width: var(--max-w); margin: 0 auto; padding: 0 1.5rem; }
.section   { padding: 6rem 0; }
.section--alt { background: var(--surface); }
.label     { font-size: .75rem; text-transform: uppercase; letter-spacing: .1em;
             color: var(--accent); font-weight: 600; margin-bottom: .5rem; }

/* ── Nav ────────────────────────────────────────────────────── */
nav {
  position: sticky; top: 0; z-index: 100;
  background: rgba(13,17,23,.9); backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  padding: 1rem 1.5rem;
  display: flex; align-items: center; justify-content: space-between;
}
.nav-logo { font-weight: 700; font-size: 1.1rem; color: var(--accent); text-decoration: none; }
.nav-links { display: flex; gap: 1.5rem; list-style: none; }
.nav-links a { color: var(--muted); text-decoration: none; font-size: .9rem;
               transition: color .2s; }
.nav-links a:hover { color: var(--text); }

/* ── Buttons ────────────────────────────────────────────────── */
.btn {
  display: inline-block; padding: .65rem 1.4rem; border-radius: var(--radius);
  font-weight: 600; font-size: .9rem; text-decoration: none; transition: all .2s;
}
.btn-primary {
  background: var(--accent); color: #000;
}
.btn-primary:hover { background: var(--accent-dim); }
.btn-ghost {
  border: 1px solid var(--border); color: var(--text);
}
.btn-ghost:hover { border-color: var(--accent); color: var(--accent); }
.btn-group { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 2rem; }

/* ── Hero ───────────────────────────────────────────────────── */
.hero {
  min-height: 90vh; display: flex; align-items: center;
  padding: 6rem 1.5rem;
  background: radial-gradient(ellipse at 60% 40%, rgba(240,165,0,.08) 0%, transparent 60%);
}
.hero-inner { max-width: var(--max-w); margin: 0 auto; }
.hero-eyebrow {
  display: inline-block; background: rgba(240,165,0,.12);
  color: var(--accent); border: 1px solid rgba(240,165,0,.3);
  padding: .3rem .8rem; border-radius: 20px; font-size: .8rem;
  font-weight: 600; letter-spacing: .05em; margin-bottom: 1.5rem;
}
.hero h1 { margin-bottom: 1rem; }
.hero h1 em { color: var(--accent); font-style: normal; }
.hero .subline { font-size: 1.2rem; color: var(--muted); max-width: 55ch;
                  margin-bottom: 2rem; }

/* ── Timeline ───────────────────────────────────────────────── */
.timeline {
  position: relative;
  padding: 2rem 0;
  overflow-x: auto;
}
.timeline-track {
  display: flex; gap: 0; align-items: flex-start;
  min-width: max-content; padding-bottom: 1rem;
}
.timeline-node {
  display: flex; flex-direction: column; align-items: center;
  width: 140px; flex-shrink: 0;
  position: relative;
}
.timeline-node::after {
  content: ''; position: absolute; top: 18px; left: 70px;
  width: 140px; height: 2px; background: var(--border); z-index: 0;
}
.timeline-node:last-child::after { display: none; }
.timeline-dot {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--surface); border: 2px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  font-size: .7rem; font-weight: 700; color: var(--muted);
  position: relative; z-index: 1; flex-shrink: 0;
}
.timeline-node.highlight .timeline-dot {
  background: var(--accent); border-color: var(--accent); color: #000;
}
.timeline-content {
  margin-top: .75rem; text-align: center; padding: 0 .5rem;
}
.timeline-content h4 { font-size: .8rem; color: var(--text); margin-bottom: .2rem; }
.timeline-content p  { font-size: .7rem; color: var(--muted); max-width: none; }

/* ── Blockquote ─────────────────────────────────────────────── */
.quote-block {
  border-left: 3px solid var(--accent);
  padding: 1.5rem 2rem; margin: 3rem 0;
  background: var(--surface); border-radius: 0 var(--radius) var(--radius) 0;
}
.quote-block blockquote {
  font-size: 1.25rem; color: var(--text); font-style: italic; margin-bottom: .75rem;
}
.quote-block cite { font-size: .85rem; color: var(--muted); font-style: normal; }

/* ── Use-Case grid ──────────────────────────────────────────── */
.uc-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem; margin: 2rem 0;
}
.uc-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 1.25rem;
}
.uc-card h4 { font-size: .9rem; margin-bottom: .4rem; }
.uc-card p  { font-size: .85rem; }
.uc-num {
  display: inline-block; background: rgba(240,165,0,.15);
  color: var(--accent); border-radius: 4px;
  font-size: .7rem; font-weight: 700; padding: .1rem .5rem;
  margin-bottom: .5rem;
}

/* ── Features grid ──────────────────────────────────────────── */
.features-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem; margin: 3rem 0;
}
.feature-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 1.75rem;
  transition: border-color .2s;
}
.feature-card:hover { border-color: var(--accent); }
.feature-icon { font-size: 1.8rem; margin-bottom: 1rem; }
.feature-card h3 { margin-bottom: .5rem; }
.feature-card p { font-size: .9rem; }

/* ── Tech badges ────────────────────────────────────────────── */
.badges { display: flex; flex-wrap: wrap; gap: .5rem; margin: 1.5rem 0; }
.badge {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 20px; padding: .3rem .9rem;
  font-size: .8rem; color: var(--muted); font-family: var(--font-mono);
}

/* ── Newton / gap section ───────────────────────────────────── */
.newton-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 2rem;
  margin: 2rem 0;
}
@media (max-width: 640px) { .newton-grid { grid-template-columns: 1fr; } }
.newton-col {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 1.5rem;
}
.newton-col.vision { border-color: var(--accent); }
.newton-col h3 { margin-bottom: 1rem; }
.newton-col ul { list-style: none; padding: 0; }
.newton-col ul li {
  padding: .4rem 0; border-bottom: 1px solid var(--border);
  font-size: .9rem; color: var(--muted);
}
.newton-col ul li:last-child { border-bottom: none; }

/* ── Tech timeline ──────────────────────────────────────────── */
.tech-timeline {
  display: flex; flex-wrap: wrap; gap: .5rem; margin: 2rem 0; align-items: center;
}
.tech-year {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: .4rem .8rem;
  font-size: .8rem; text-align: center;
}
.tech-year span { display: block; color: var(--accent); font-weight: 700;
                   font-size: .7rem; }
.tech-arrow { color: var(--muted); font-size: 1rem; }

/* ── Setup steps ────────────────────────────────────────────── */
.steps { counter-reset: step; margin: 2rem 0; }
.step {
  counter-increment: step;
  display: flex; gap: 1.5rem; margin-bottom: 2.5rem;
}
.step-num {
  flex-shrink: 0; width: 2rem; height: 2rem; border-radius: 50%;
  background: var(--accent); color: #000;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: .9rem;
}
.step-body h3 { margin-bottom: .5rem; }
.step-body pre {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 1rem; margin-top: .75rem;
  font-family: var(--font-mono); font-size: .85rem; overflow-x: auto;
  color: var(--text);
}

/* ── German callout ─────────────────────────────────────────── */
.de-note {
  background: rgba(240,165,0,.07); border: 1px solid rgba(240,165,0,.25);
  border-radius: var(--radius); padding: .75rem 1rem;
  font-size: .85rem; color: var(--muted); margin-top: .75rem;
}
.de-note strong { color: var(--accent); }

/* ── Footer ─────────────────────────────────────────────────── */
footer {
  background: var(--surface); border-top: 1px solid var(--border);
  padding: 3rem 1.5rem; text-align: center;
}
.footer-links { display: flex; justify-content: center; gap: 2rem;
                 flex-wrap: wrap; margin-bottom: 1.5rem; }
.footer-links a { color: var(--muted); text-decoration: none; font-size: .9rem;
                   transition: color .2s; }
.footer-links a:hover { color: var(--accent); }
footer p { font-size: .8rem; color: var(--muted); margin: 0 auto; }

/* ── Responsive ─────────────────────────────────────────────── */
@media (max-width: 768px) {
  .nav-links { display: none; }
  h1 { font-size: 2rem; }
}
```

**Step 2: Create `index.html`** — paste this complete file:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Phil – Knowledge Navigator</title>
  <meta name="description" content="A student reimagining of Apple's 1987 Knowledge Navigator. Built with FastAPI, React and Claude AI.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,600;0,9..40,700;1,9..40,400&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>

<!-- ── Navigation ──────────────────────────────────────────── -->
<nav>
  <a href="#" class="nav-logo">Phil ✦</a>
  <ul class="nav-links">
    <li><a href="#lineage">The Lineage</a></li>
    <li><a href="#vision">1987 Vision</a></li>
    <li><a href="#gap">The Gap</a></li>
    <li><a href="#phil">Phil 2026</a></li>
    <li><a href="#start">Get Started</a></li>
    <li><a href="." class="btn btn-ghost" style="padding:.4rem .9rem">Docs →</a></li>
  </ul>
</nav>

<!-- ── Hero ────────────────────────────────────────────────── -->
<section class="hero">
  <div class="hero-inner">
    <span class="hero-eyebrow">Open Student Project · THWS / DHBW · 2026</span>
    <h1>Standing on the<br><em>Shoulders of Giants</em></h1>
    <p class="subline">
      Apple imagined a personal knowledge assistant in 1987 and named it Phil.
      Decades of visionary thinking made it possible.
      In 2026, we rebuilt it — as a working system, as a tribute.
    </p>
    <div class="btn-group">
      <a href="#lineage" class="btn btn-primary">Explore the Story</a>
      <a href="#start" class="btn btn-ghost">Get Started</a>
      <a href="https://github.com/swrobuts/phil-knowledge-navigator" class="btn btn-ghost" target="_blank">GitHub →</a>
    </div>
  </div>
</section>

<!-- ── Section 1: The Lineage ──────────────────────────────── -->
<section class="section" id="lineage">
  <div class="container">
    <p class="label">Intellectual Lineage</p>
    <h2>Every idea has ancestors.</h2>
    <p style="margin: 1rem 0 2rem;">
      The Knowledge Navigator did not emerge from nowhere. It was the crystallisation
      of decades of visionary thinking — from analogue knowledge networks to interactive
      computing, from the first chatbot to the personal computer. Here is the lineage
      that made Phil possible.
    </p>

    <div class="timeline">
      <div class="timeline-track">

        <div class="timeline-node">
          <div class="timeline-dot">1935</div>
          <div class="timeline-content">
            <h4>Mundaneum</h4>
            <p>Paul Otlet — a global knowledge network on index cards</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1937</div>
          <div class="timeline-content">
            <h4>World Brain</h4>
            <p>H.G. Wells — a living, always-updated world encyclopaedia</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1945</div>
          <div class="timeline-content">
            <h4>Memex</h4>
            <p>Vannevar Bush — a desk that stores and links documents associatively</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1950</div>
          <div class="timeline-content">
            <h4>Turing Test</h4>
            <p>Alan Turing — can machines think? The measure for AI to this day</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1955</div>
          <div class="timeline-content">
            <h4>Artificial Intelligence</h4>
            <p>John McCarthy — coined the term at the Dartmouth Conference</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1960</div>
          <div class="timeline-content">
            <h4>Man–Computer Symbiosis</h4>
            <p>J.C.R. Licklider — interactive cooperation between human and machine</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1963</div>
          <div class="timeline-content">
            <h4>Sketchpad</h4>
            <p>Ivan Sutherland — first interactive computer graphics, direct manipulation</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1966</div>
          <div class="timeline-content">
            <h4>ELIZA</h4>
            <p>Joseph Weizenbaum — first chatbot, machines simulating empathy</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1968</div>
          <div class="timeline-content">
            <h4>Mother of All Demos</h4>
            <p>Douglas Engelbart — mouse, windows, hypertext, video conferencing</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1972</div>
          <div class="timeline-content">
            <h4>Dynabook</h4>
            <p>Alan Kay — a portable learning device anticipating tablets by 35 years</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1974</div>
          <div class="timeline-content">
            <h4>Xanadu / Hypertext</h4>
            <p>Ted Nelson — a global document network; hypertext before the web</p>
          </div>
        </div>

        <div class="timeline-node">
          <div class="timeline-dot">1986</div>
          <div class="timeline-content">
            <h4>Society of Mind</h4>
            <p>Marvin Minsky — intelligence as the interplay of many simple agents</p>
          </div>
        </div>

        <div class="timeline-node highlight">
          <div class="timeline-dot">1987</div>
          <div class="timeline-content">
            <h4>Knowledge Navigator</h4>
            <p>John Sculley / Apple — united all of this. Named the agent <strong>Phil</strong>.</p>
          </div>
        </div>

        <div class="timeline-node highlight">
          <div class="timeline-dot">2026</div>
          <div class="timeline-content">
            <h4>Phil (this project)</h4>
            <p>Real code. Real AI. Same name.</p>
          </div>
        </div>

      </div>
    </div>

    <div class="quote-block">
      <blockquote>
        "A future-generation Macintosh might well be a wonderful fantasy machine called
        the Knowledge Navigator, a discoverer of worlds, a tool as galvanizing as
        the printing press."
      </blockquote>
      <cite>— John Sculley, <em>Odyssey: Pepsi to Apple</em>, 1987</cite>
    </div>

    <p style="font-size:.85rem; color:var(--muted); margin-top:1rem;">
      Sources: Dubberly, H. (2024): <em>Making Knowledge Navigator</em> ·
      Sculley, J., Byrne, J. A. (1987): <em>Odyssey: Pepsi to Apple</em>, Harper &amp; Row
    </p>
  </div>
</section>

<!-- ── Section 2: The 1987 Vision ──────────────────────────── -->
<section class="section section--alt" id="vision">
  <div class="container">
    <p class="label">Apple · 1987</p>
    <h2>The Vision</h2>
    <p style="margin: 1rem 0 2rem;">
      In 1987, Apple released a concept video showing what a personal knowledge assistant
      could be. It was fiction — none of the required technology existed yet.
      But the vision was precise, and the name of the assistant was already <strong>Phil</strong>.
    </p>

    <!-- YouTube thumbnail — linked, not embedded/autoplay -->
    <a href="https://www.youtube.com/watch?v=HGYFEI6uLy0" target="_blank"
       style="display:block; max-width:600px; margin:0 auto 3rem; text-decoration:none;">
      <div style="background:var(--bg); border:1px solid var(--border); border-radius:var(--radius);
                  padding:3rem; text-align:center; cursor:pointer; transition:border-color .2s;"
           onmouseover="this.style.borderColor='var(--accent)'"
           onmouseout="this.style.borderColor='var(--border)'">
        <div style="font-size:3rem; margin-bottom:1rem;">▶</div>
        <p style="color:var(--muted); font-size:.9rem; margin:0;">
          Apple Knowledge Navigator Concept Video (1987)<br>
          <span style="font-size:.8rem;">Opens on YouTube</span>
        </p>
      </div>
    </a>

    <h3 style="margin-bottom:1.5rem;">Eight use cases Apple demonstrated</h3>
    <div class="uc-grid">
      <div class="uc-card">
        <div class="uc-num">UC 1</div>
        <h4>Conversational AI Agent</h4>
        <p>Natural language dialogue with an intelligent "bowtie avatar" — proactive, context-aware</p>
      </div>
      <div class="uc-card">
        <div class="uc-num">UC 2</div>
        <h4>Calendar Management</h4>
        <p>Automatic scheduling, reminders, and agenda briefings</p>
      </div>
      <div class="uc-card">
        <div class="uc-num">UC 3</div>
        <h4>Video Conferencing</h4>
        <p>Real-time video call with a colleague for collaborative data analysis</p>
      </div>
      <div class="uc-card">
        <div class="uc-num">UC 4</div>
        <h4>Knowledge Research</h4>
        <p>Intelligent search across scientific databases and sources</p>
      </div>
      <div class="uc-card">
        <div class="uc-num">UC 5</div>
        <h4>Data Visualisation</h4>
        <p>Dynamic, interactive charts and geographic simulations on demand</p>
      </div>
      <div class="uc-card">
        <div class="uc-num">UC 6</div>
        <h4>Document Summarisation</h4>
        <p>Automatic briefing from documents, messages and research papers</p>
      </div>
      <div class="uc-card">
        <div class="uc-num">UC 7</div>
        <h4>Simulation</h4>
        <p>Modelling and visualisation of complex scenarios (e.g. deforestation over time)</p>
      </div>
      <div class="uc-card">
        <div class="uc-num">UC 8</div>
        <h4>Multimodal Interaction</h4>
        <p>Touch, voice, and gesture as input methods — seamless delegation of tasks</p>
      </div>
    </div>
  </div>
</section>

<!-- ── Section 3: The Gap ───────────────────────────────────── -->
<section class="section" id="gap">
  <div class="container">
    <p class="label">1987 – 2022</p>
    <h2>The Gap — And the Attempt</h2>
    <p style="margin: 1rem 0 2rem;">
      The vision was clear. The technology was not. Apple tried — honestly — with the Newton
      MessagePad in 1993. It failed, not because the idea was wrong, but because the decade
      was wrong. The Newton is not a failure story. It is proof that the idea was worth pursuing.
    </p>

    <div class="newton-grid">
      <div class="newton-col vision">
        <h3>Vision: Knowledge Navigator (1987)</h3>
        <ul>
          <li>Intelligent AI agent with natural language</li>
          <li>Global knowledge access via network</li>
          <li>Touch interaction — tablet form factor</li>
          <li>Personalised, learns from the user</li>
        </ul>
      </div>
      <div class="newton-col">
        <h3>Reality: Apple Newton (1993)</h3>
        <ul>
          <li>$699 entry price — too high for unclear value</li>
          <li>Handwriting recognition failed publicly (Simpsons parody)</li>
          <li>No internet, no wireless sync, no ecosystem</li>
          <li>Released 14 months before it was ready</li>
        </ul>
      </div>
    </div>

    <p style="margin: 2rem 0 1rem; font-weight:600; color:var(--text);">
      What had to be invented before Phil could exist:
    </p>
    <div class="tech-timeline">
      <div class="tech-year"><span>1990</span>Speech recognition</div>
      <div class="tech-arrow">→</div>
      <div class="tech-year"><span>1993</span>World Wide Web</div>
      <div class="tech-arrow">→</div>
      <div class="tech-year"><span>2006</span>Cloud computing</div>
      <div class="tech-arrow">→</div>
      <div class="tech-year"><span>2007</span>Touch (iPhone)</div>
      <div class="tech-arrow">→</div>
      <div class="tech-year"><span>2010</span>Tablet (iPad)</div>
      <div class="tech-arrow">→</div>
      <div class="tech-year"><span>2011</span>Siri</div>
      <div class="tech-arrow">→</div>
      <div class="tech-year"><span>2022</span>ChatGPT</div>
      <div class="tech-arrow">→</div>
      <div class="tech-year" style="border-color:var(--accent); color:var(--accent)"><span>2026</span>Phil ✦</div>
    </div>
  </div>
</section>

<!-- ── Section 4: Phil 2026 ─────────────────────────────────── -->
<section class="section section--alt" id="phil">
  <div class="container">
    <p class="label">Phil 2026</p>
    <h2>Today, the technology finally caught up.</h2>
    <p style="margin: 1rem 0;">
      Phil is a working personal information manager — not a concept video, not a demo.
      It manages email, calendar, tasks and knowledge using today's AI tools.
      It doesn't do everything Apple envisioned. But it does what matters most, right now.
    </p>

    <div class="features-grid">
      <div class="feature-card">
        <div class="feature-icon">📬</div>
        <h3>Mail Triage</h3>
        <p>Phil reads your inbox and categorises messages by priority: VIP / Action Required / FYI / Noise. Each mail gets a summary and a concrete recommended action. Powered by Claude.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📊</div>
        <h3>Dashboard</h3>
        <p>A daily briefing at a glance: unread mails by category, today's calendar events, pending tasks, and analytical tiles showing your communication patterns.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📅</div>
        <h3>Calendar</h3>
        <p>Natural-language calendar search. Ask "What's next week?" or "When is the faculty meeting?" Phil fetches a full year of events and answers from context.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🤝</div>
        <h3>Meeting Preparation</h3>
        <p>Given a calendar event, Phil identifies participants, searches related emails via RAG, and drafts a structured briefing: attendees, relevant messages, proposed agenda.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🧠</div>
        <h3>Memory &amp; Learning</h3>
        <p>Phil remembers facts about you across sessions, stored in SQLite + ChromaDB. Thumbs up/down feedback drives RLHF-style learning. Facts are visible and editable.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🔍</div>
        <h3>Semantic Search</h3>
        <p>Emails and attachments (PDF, DOCX) are indexed in a vector store. Phil can retrieve semantically similar past correspondence even when keyword search fails.</p>
      </div>
    </div>
  </div>
</section>

<!-- ── Section 5: Tech Stack + Prompts ─────────────────────── -->
<section class="section" id="tech">
  <div class="container">
    <p class="label">How It's Built</p>
    <h2>Tech Stack</h2>
    <p style="margin: 1rem 0 1.5rem;">
      Phil is built entirely on open-source tooling and standard cloud APIs.
      No proprietary platform lock-in. Everything you need is in the repository.
    </p>
    <p style="font-weight:600; color:var(--text); margin-bottom:.5rem;">Backend</p>
    <div class="badges">
      <span class="badge">FastAPI</span>
      <span class="badge">Python 3.12</span>
      <span class="badge">Anthropic Claude API</span>
      <span class="badge">ChromaDB</span>
      <span class="badge">SQLite</span>
      <span class="badge">RDFlib</span>
      <span class="badge">pdfplumber</span>
      <span class="badge">exchangelib</span>
    </div>
    <p style="font-weight:600; color:var(--text); margin-bottom:.5rem;">Frontend</p>
    <div class="badges">
      <span class="badge">React 18</span>
      <span class="badge">TypeScript</span>
      <span class="badge">Vite</span>
      <span class="badge">CSS Modules</span>
    </div>
    <p style="font-weight:600; color:var(--text); margin-bottom:.5rem;">Integrations</p>
    <div class="badges">
      <span class="badge">Google Workspace</span>
      <span class="badge">DuckDuckGo Search</span>
      <span class="badge">PyHafas (DB)</span>
    </div>
    <p style="margin-top:2rem;">
      Every LLM prompt in Phil follows the <strong>CO-STAR framework</strong>
      (Context · Objective · Style · Tone · Audience · Response format).
      <a href="prompts.html" style="color:var(--accent)">See all prompts →</a>
    </p>
  </div>
</section>

<!-- ── Section 6: Get Started ──────────────────────────────── -->
<section class="section section--alt" id="start">
  <div class="container">
    <p class="label">For Students</p>
    <h2>Rebuild Phil yourself.</h2>
    <p style="margin: 1rem 0 2rem;">
      You need Python 3.11+, Node 20+, an Anthropic API key and a Google Workspace account.
      No Docker required.
    </p>
    <div class="de-note" style="margin-bottom:2rem;">
      <strong>DE:</strong> Du brauchst Python 3.11+, Node 20+, einen Anthropic API-Key und ein Google Workspace Konto.
      Docker ist nicht erforderlich.
    </div>

    <div class="steps">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-body">
          <h3>Clone &amp; install dependencies</h3>
          <p>Get the code and install both Python and JavaScript dependencies.</p>
          <pre>git clone https://github.com/swrobuts/phil-knowledge-navigator
cd phil-knowledge-navigator
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..</pre>
        </div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-body">
          <h3>Configure your <code>.env</code></h3>
          <p>Copy the example file and add your credentials. The only required key is <code>ANTHROPIC_API_KEY</code> for basic chat. Google credentials unlock mail and calendar features.</p>
          <pre>cp backend/.env.example backend/.env
# Edit backend/.env and add:
# ANTHROPIC_API_KEY=sk-ant-...</pre>
          <div class="de-note">
            <strong>DE:</strong> Die Datei <code>.env.example</code> erklärt jeden Parameter.
            Für einen ersten Start reicht der Anthropic API-Key.
          </div>
        </div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-body">
          <h3>Run Phil locally</h3>
          <p>Start the backend and frontend in two terminal tabs.</p>
          <pre># Terminal 1 — Backend
uvicorn backend.main:app --reload

# Terminal 2 — Frontend
cd frontend && npm run dev

# Open → http://localhost:5173</pre>
        </div>
      </div>
    </div>

    <a href="setup.html" class="btn btn-primary">Full Setup Guide →</a>
    <a href="https://github.com/swrobuts/phil-knowledge-navigator" class="btn btn-ghost" target="_blank" style="margin-left:1rem;">View on GitHub →</a>
  </div>
</section>

<!-- ── Footer ───────────────────────────────────────────────── -->
<footer>
  <div class="footer-links">
    <a href=".">Documentation</a>
    <a href="story.html">The Story</a>
    <a href="prompts.html">CO-STAR Prompts</a>
    <a href="https://github.com/swrobuts/phil-knowledge-navigator" target="_blank">GitHub</a>
  </div>
  <p>
    Phil is a student project at THWS / DHBW in the course <em>Datenbasierte Fallstudien</em>.
    It is not affiliated with Apple Inc.<br>
    MIT Licence · Built with Claude Code by Anthropic.
  </p>
</footer>

</body>
</html>
```

**Step 3: Verify locally**

Open `index.html` directly in a browser. Check:
- Timeline scrolls horizontally on narrow screens
- All section anchors work (nav links)
- YouTube thumbnail link opens correctly
- No broken layout on mobile (resize browser to 375px)

**Step 4: Commit**

```bash
git add index.html assets/style.css
git commit -m "feat: landing page — hero, lineage, vision, gap, features, get started"
git push origin main
```

---

## Task 3: MkDocs — story.md (The Intellectual Lineage)

**Files:**
- Create: `docs/story.md`

**Step 1: Create `docs/story.md`**

```markdown
# The Intellectual Lineage

> "The Knowledge Navigator did not emerge from nowhere.
> It was the crystallisation of decades of visionary thinking."
> — Dubberly, H. (2024): *Making Knowledge Navigator*

Apple's Knowledge Navigator concept video appeared in 1987. But the ideas it embodied
had been building for over fifty years, contributed by thinkers across computing,
library science, and cognitive science.

This page traces that lineage — not to diminish Apple's achievement, but to properly credit
the giants on whose shoulders it stood. And on whose shoulders Phil stands too.

---

## The Pioneers (1935–1987)

### Paul Otlet · Mundaneum · 1935
Belgian bibliographer Paul Otlet built the Mundaneum — a global knowledge network
on 16 million index cards. He envisioned a universal interconnected encyclopedia,
a "réseau mondial" that anticipates today's internet by 60 years.
*Source: Dubberly, H. (2024): Making Knowledge Navigator*

### H.G. Wells · World Brain · 1937
Wells called for a "Permanent World Encyclopaedia" — a living, continuously updated
global knowledge base accessible to everyone. A direct precursor to Wikipedia.
*Wells, H.G. (1937): World Brain, Doubleday*

### Vannevar Bush · Memex · 1945
Bush described the Memex — a desk apparatus that stores documents on microfilm
and allows associative linking between them. He called it "thinking by association,
the way the human mind actually works." This is hypertext, invented conceptually in 1945.
*Bush, V. (1945): As We May Think, The Atlantic*

### Alan Turing · Turing Test · 1950
Turing asked: "Can machines think?" His Imitation Game provided the first operational
definition of machine intelligence. The question remains central to AI research to this day.
*Turing, A. (1950): Computing Machinery and Intelligence, Mind*

### John McCarthy · Artificial Intelligence · 1955
McCarthy coined the term "Artificial Intelligence" at the Dartmouth Summer Research Project.
He set the agenda: machines should simulate human intelligence. Everything that followed
builds on this framing.
*McCarthy, J. et al. (1955): A Proposal for the Dartmouth Summer Research Project on AI*

### J.C.R. Licklider · Man–Computer Symbiosis · 1960
Licklider described a future where humans and computers collaborate interactively —
not automation, but augmentation. He also co-created ARPANET, the precursor to the internet.
*Licklider, J.C.R. (1960): Man-Computer Symbiosis, IRE Transactions*

### Ivan Sutherland · Sketchpad · 1963
Sutherland built the first interactive computer graphics system. Users could draw directly
on screen with a light pen — direct manipulation decades before the mouse.
*Sutherland, I. (1963): Sketchpad: A Man-Machine Graphical Communication System, MIT*

### Joseph Weizenbaum · ELIZA · 1966
Weizenbaum built the first chatbot: ELIZA simulated a therapist and shocked its creator
by how readily people attributed empathy and understanding to a simple pattern-matching program.
A warning that remains relevant today.
*Weizenbaum, J. (1966): ELIZA — A Computer Program for the Study of Natural Language Communication Between Man and Machine, CACM*

### Douglas Engelbart · The Mother of All Demos · 1968
On December 9, 1968, Engelbart demonstrated the mouse, overlapping windows, hypertext,
collaborative editing, and video conferencing — all at once, all live, all working.
It is the most consequential 90-minute demonstration in computing history.
*Engelbart, D. (1968): A Research Center for Augmenting Human Intellect, SRI International*

### Alan Kay · Dynabook · 1972
Kay designed the Dynabook — a thin, portable, personal computer for children.
Tablet-sized, networked, running interactive media. He built it at Xerox PARC.
The iPad appeared 38 years later.
*Kay, A. (1972): A Personal Computer for Children of All Ages, Xerox PARC*

### Ted Nelson · Xanadu & Hypertext · 1974
Nelson invented the word "hypertext" and designed Xanadu — a global, non-hierarchical
document network with two-way links, version history, and transclusion.
The web implemented a simplified version of his ideas.
*Nelson, T. (1974): Dream Machines / Computer Lib, self-published*

### Marvin Minsky · Society of Mind · 1986
Minsky described human intelligence as the emergent result of many simple interacting agents.
This idea — that complex behaviour arises from simple components — underlies much of
modern AI architecture, including multi-agent systems.
*Minsky, M. (1986): The Society of Mind, Simon & Schuster*

---

## The Cultural Context

Science fiction shaped the imagination of the engineers and designers who built these systems.
The Knowledge Navigator drew on a shared cultural vocabulary of intelligent machines:

- **The Jetsons (1962)** — Rosie the robot-butler, video calls, a fully automated home
- **Star Trek (1966)** — a starship computer that responds to natural speech
- **2001: A Space Odyssey (1968)** — HAL 9000: autonomous control, lip-reading, self-interest; a warning
- **Neuromancer (1984)** — Gibson coined "cyberspace"; hackers enter a digital matrix with emergent AI
- **The Terminator (1984)** — Skynet becomes self-aware; the dystopian counterweight

---

## Apple's Synthesis (1987)

In 1987, John Sculley's Apple united fifty years of visionary thinking into a single
9-minute concept video. Hugh Dubberly, then a designer at Apple, led the production.

Five key technologies Sculley identified as necessary (which did not yet exist):

1. **Communication infrastructure** — global networking of computers and databases
2. **3D real-time animation** — visualisation of complex models
3. **Database technologies** — structured, comprehensive knowledge access
4. **Artificial Intelligence** — agents that recognise preferences and suggest strategies
5. **Hypermedia** — multimodal linking of text, graphics, audio and video

The agent in the video who manages all of this was already named **Phil**.

*Sculley, J., Byrne, J.A. (1987): Odyssey: Pepsi to Apple, Harper & Row, pp. 403–425*
*Dubberly, H. (2024): Making Knowledge Navigator. Retrieved 12.01.2026*

---

## Phil 2026

In 2026, for the first time, all five of Sculley's required technologies exist and are
accessible via standard APIs and open-source libraries.

Phil is a student project that implements a working subset of the Knowledge Navigator vision.
It does not do everything the 1987 video showed. It does not pretend to.
But it is real — a running system, built with the tools of its time,
in the spirit of all the thinkers who came before.
```

**Step 2: Build and verify**

```bash
mkdocs serve
# Open http://127.0.0.1:8000/story/
# Verify: all sections render, headings in nav sidebar, sources display correctly
```

**Step 3: Commit**

```bash
git add docs/story.md
git commit -m "docs: story.md — intellectual lineage from Otlet 1935 to Phil 2026"
git push origin main
```

---

## Task 4: MkDocs — use-cases.md

**Files:**
- Create: `docs/use-cases.md`

**Step 1: Create `docs/use-cases.md`**

```markdown
# Use Cases: 1987 vs. 2026

Apple's 1987 concept video demonstrated eight concrete use cases.
What was then pure fiction is now technically realisable — though not always by a single system.

This page maps each Apple use case to what exists in 2026, distinguishing clearly
between what **Phil implements directly** and what today's other tools provide.

---

| # | Apple 1987 | Phil 2026 | Other Tools |
|---|-----------|-----------|-------------|
| 1 | **Conversational AI Agent** — natural language dialogue, proactive suggestions | ✅ Phil Chat with streaming, context injection, proactive next steps | ChatGPT, Claude.ai |
| 2 | **Calendar Management** — scheduling, reminders, agenda | ✅ Calendar view, natural-language search, meeting briefings | Google Calendar, Siri |
| 3 | **Video Conferencing** — real-time video with colleague | — Not in Phil | Zoom, Teams, Google Meet |
| 4 | **Knowledge Research** — intelligent search in scientific databases | ✅ Semantic RAG search over emails + attachments | Perplexity, Semantic Scholar |
| 5 | **Data Visualisation** — interactive charts, geographic simulations | — Not in Phil (see WorldHappiness project) | ChatGPT Code Interpreter, Plotly |
| 6 | **Document Summarisation** — briefing from papers and messages | ✅ Mail summaries, attachment extraction, meeting prep briefings | NotebookLM, Claude |
| 7 | **Simulation** — complex scenario modelling | — Not in Phil | Specialist tools |
| 8 | **Multimodal Interaction** — touch, voice, gesture | — Web UI only; no voice input | Siri, Alexa, Google Assistant |

---

## What Phil Does Well

Phil focuses on the daily information management problem that the 1987 video showed in its
opening minutes: managing the flow of messages, understanding what needs attention,
and preparing for the day ahead.

- **Mail triage** — categorise, prioritise, summarise, recommend actions (UC 1, 2, 6)
- **Calendar awareness** — understand what is coming and why it matters (UC 2)
- **Meeting preparation** — briefing a user before a meeting using past correspondence (UC 4, 6)
- **Memory** — learning facts about the user's world across sessions (UC 1)
- **RAG search** — finding relevant past emails semantically (UC 4)

## What Phil Does Not Do (and why)

Phil does not implement video conferencing (UC 3), data visualisation (UC 5),
complex simulation (UC 7) or voice input (UC 8). This is not a shortcoming — it is a scope decision.
These are better served by dedicated tools. Phil's value is in the daily information layer.

!!! note "DE — Für Studierende"
    Phil ist kein Alleskönner. Jede Funktion wurde bewusst ausgewählt: Was bringt den
    größten Mehrwert im Hochschulalltag? Die Use Cases 3, 5, 7, 8 sind im Vortrag
    konzeptuelle Parallelen (Zoom für UC3, Perplexity für UC4 usw.) — nicht Ziele für Phil selbst.
```

**Step 2: Verify**

```bash
mkdocs serve
# Open http://127.0.0.1:8000/use-cases/
# Check: table renders correctly, admonition box displays
```

**Step 3: Commit**

```bash
git add docs/use-cases.md
git commit -m "docs: use-cases.md — 1987 Apple UCs vs Phil 2026 honest mapping"
git push origin main
```

---

## Task 5: MkDocs — features pages (6 files)

**Files:**
- Create: `docs/features/index.md`
- Create: `docs/features/mail-triage.md`
- Create: `docs/features/dashboard.md`
- Create: `docs/features/calendar.md`
- Create: `docs/features/meeting-prep.md`
- Create: `docs/features/memory-learning.md`
- Create: `docs/features/rag-search.md`

**Step 1: Create `docs/features/index.md`**

```markdown
# Features

Phil implements six core features, all oriented around one goal:
help you manage your daily information flow without drowning in it.

| Feature | What it does |
|---------|-------------|
| [Mail Triage](mail-triage.md) | Categorise and summarise incoming email |
| [Dashboard](dashboard.md) | Daily overview of mail, calendar, tasks |
| [Calendar](calendar.md) | Natural-language calendar queries |
| [Meeting Preparation](meeting-prep.md) | Briefing before every appointment |
| [Memory & Learning](memory-learning.md) | Persistent facts, RLHF feedback |
| [Semantic Search](rag-search.md) | Vector search over emails and attachments |
```

**Step 2: Create `docs/features/mail-triage.md`**

```markdown
# Mail Triage

Phil's core feature: read your inbox and decide what matters.

## How it works

1. Phil fetches emails from Google Workspace via the Exchange protocol
2. Each email is analysed by Claude using the CO-STAR triage prompt
3. A category, priority score, 2-sentence summary, and recommended action are returned
4. Results appear in the Mail view, sorted by priority

## Categories

| Category | Priority | When |
|----------|----------|------|
| VIP | 1 | Deanery, superiors, important partners |
| Action Required | 2 | Students, colleagues with concrete requests |
| FYI | 3 | Newsletters, informational only |
| Noise | 4 | Spam, advertising, irrelevant |

## Attachment extraction

If an email has attachments (PDF, DOCX), Phil extracts the text and includes
a 3-sentence summary in the triage result. Powered by `pdfplumber` and `python-docx`.

## Sentiment analysis

Each email also receives a sentiment score from -1.0 (very negative) to +1.0 (very positive).
This appears as a colour-coded indicator on the mail card.

## API endpoint

`POST /api/triage-mails` — fetches recent mails, runs triage, returns categorised results.

!!! note "DE"
    Phil liest deine E-Mails, kategorisiert sie nach Priorität und fasst jede in zwei Sätzen zusammen.
    Du siehst in 5 Sekunden, was sofortige Aufmerksamkeit braucht.
```

**Step 3: Create `docs/features/dashboard.md`**

```markdown
# Dashboard

The Dashboard is Phil's daily briefing — a single-screen overview of what matters.

## Panels

- **Unread mails** — count by category (VIP / Action Required / FYI / Noise)
- **Today's calendar** — next appointments with time, title and location
- **Pending tasks** — tasks extracted from mails or created manually
- **Analytics tiles** — communication patterns, mail load trends

## Context panel

Clicking a calendar event opens the context panel on the right: Phil fetches a
meeting briefing (participants, related mails, agenda suggestion) in real time.

## Design

The Dashboard uses a dark, card-based layout with colour-coded priority badges.
The left sidebar shows navigation with notification badges for unread counts.
```

**Step 4: Create `docs/features/calendar.md`**

```markdown
# Calendar

Phil integrates with Google Calendar via the `exchangelib` library,
fetching up to 365 days ahead and 180 days back.

## Natural-language queries

Ask Phil in the chat:

- *"What's on next Tuesday?"*
- *"When is the faculty board meeting?"*
- *"Do I have anything with [name] this week?"*

Phil detects calendar-related keywords (`_calendar_keywords()` in `main.py`),
fetches your full calendar context, and answers from that context rather than
generating plausible-sounding (but potentially wrong) dates.

## Anti-hallucination design

A dedicated `KALENDERSUCHE` block in the context prompt is marked as authoritative.
If Phil's answer contradicts the data in this block, it must defer to the data.
This prevents the LLM from inventing appointments that don't exist.

!!! note "DE"
    Phil liest deinen Google-Kalender und beantwortet Fragen dazu.
    Halluzinationen werden durch einen expliziten Autoritätsblock im Prompt verhindert.
```

**Step 5: Create `docs/features/meeting-prep.md`**

```markdown
# Meeting Preparation

Before any calendar event, Phil can prepare a structured briefing.

## What the briefing contains

```
## 👤 Participants
Names extracted from the event title and description

## 📬 Recent Mails
Emails related to the meeting (retrieved via RAG, similarity ≥ 60%)

## 📋 Agenda Suggestion
3–5 concrete points based on the event and related correspondence
```

## How it works

1. Phil parses the event title to extract person names (regex pattern `mit [Name]`)
2. A RAG query searches past emails for relevant correspondence
3. The result is sent to Claude with the `BRIEFING_SYSTEM` prompt
4. Response streams back to the UI in real time (Server-Sent Events)

## Trigger

Click the calendar event in the Dashboard or Calendar view → "Prepare Briefing" button.

!!! note "DE"
    Vor jedem Termin bereitet Phil ein kompaktes Briefing vor:
    Wer kommt? Welche Mails gab es zuletzt? Was sollte auf die Agenda?
```

**Step 6: Create `docs/features/memory-learning.md`**

```markdown
# Memory & Learning

Phil remembers facts about your world across sessions.

## How memory works

After each chat exchange, Phil extracts up to 3 new facts using the
`FACT_EXTRACTION_SYSTEM` prompt. Facts are stored in two layers:

1. **SQLite** — structured storage: `fact_id`, `text`, `category`, `confidence`, `source_ref`
2. **ChromaDB** — vector embeddings for semantic similarity search

## Categories

`Person` · `Projekt` · `Konzept` · `Prozedur` · `Ort`

## RLHF feedback

Every Phil chat bubble has a 👍 / 👎 button. Thumbs up increases confidence;
thumbs down decreases it. Facts below a confidence threshold are suppressed
from context injection.

## Memory view

The Memory tab shows all stored facts with:
- Confidence bar (visual)
- Category badge
- Source message reference
- Edit / Delete controls
- Filter by category

## Context injection

At chat time, the top-5 most relevant facts (by semantic similarity to the user's
question) are injected into the context as a `MEMORY` block before Phil responds.

!!! note "DE"
    Phil merkt sich Fakten aus euren Gesprächen (Personen, Projekte, Zusammenhänge)
    und nutzt sie beim nächsten Mal als Kontext. Daumen hoch/runter steuert das Lernen.
```

**Step 7: Create `docs/features/rag-search.md`**

```markdown
# Semantic Search (RAG)

Phil uses Retrieval-Augmented Generation to find relevant past emails
even when keyword search would fail.

## The problem RAG solves

A keyword search for "budget" misses an email titled "Cost allocation for Q3."
RAG finds it because the vector embeddings are semantically similar.

## How it works

1. When a mail is triaged, its text (subject + body + attachment summaries) is embedded
   using `text-embedding-3-small` (OpenAI) or equivalent
2. The embedding is stored in ChromaDB at `/tmp/phil_chroma`
3. At query time, the user's question is embedded and the top-3 nearest neighbours
   are retrieved
4. These are injected into the chat context as `MAILHISTORIE` blocks

## Vector store location

ChromaDB stores its files at `/tmp/phil_chroma` to avoid OneDrive sync conflicts
(memory-mapped HNSW files must not live on network drives).

## Ontology layer

In addition to vector search, Phil maintains an RDF ontology store (`OntologyStore`)
that maps extracted entities (persons, projects, deadlines) as structured triples.
This allows precise graph queries alongside fuzzy semantic search.

!!! note "DE"
    Phil kann deine E-Mails semantisch durchsuchen — nicht nur nach Stichwörtern,
    sondern nach Bedeutung. Ähnliche Mails aus der Vergangenheit werden automatisch
    als Kontext eingeblendet.
```

**Step 8: Build and verify all feature pages**

```bash
mkdocs serve
# Check each feature page: http://127.0.0.1:8000/features/mail-triage/ etc.
# Verify: admonitions render, code blocks have copy button, nav sidebar shows all 6
```

**Step 9: Commit**

```bash
git add docs/features/
git commit -m "docs: all 6 feature pages — mail triage, dashboard, calendar, meeting prep, memory, RAG"
git push origin main
```

---

## Task 6: MkDocs — setup.md (Local Setup Guide)

**Files:**
- Create: `docs/setup.md`

**Step 1: Create `docs/setup.md`**

```markdown
# Getting Started

Run Phil locally — no Docker required.

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | `python3 --version` |
| Node.js | 20+ | `node --version` |
| Anthropic API key | — | [console.anthropic.com](https://console.anthropic.com) |
| Google Workspace account | — | Gmail + Google Calendar access |

!!! note "DE — Voraussetzungen"
    Python 3.11+, Node 20+, ein Anthropic API-Key und ein Google Workspace Konto.
    Die `.env.example` erklärt jeden Parameter.

---

## Step 1: Clone and install

```bash
git clone https://github.com/swrobuts/phil-knowledge-navigator.git
cd phil-knowledge-navigator

# Python dependencies
pip install -r backend/requirements.txt

# JavaScript dependencies
cd frontend
npm install
cd ..
```

---

## Step 2: Configure `.env`

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Your Claude API key |
| `OPENAI_API_KEY` | Optional | For OpenAI embeddings (ChromaDB) |
| `GOG_ACCOUNT` | For mail/calendar | Your Google Workspace email |
| `GOG_KEYRING_PASSWORD` | For mail/calendar | App password or OAuth token |
| `LOCAL_LLM_ENDPOINT` | Optional | LM Studio local LLM endpoint |
| `LOCAL_LLM_MODEL` | Optional | e.g. `qwen2.5-32b-instruct` |

!!! warning
    Never commit your `.env` file. It is listed in `.gitignore`.
    The repo only contains `.env.example` with placeholder values.

---

## Step 3: Google Workspace authentication

Phil connects to Gmail and Google Calendar via the Exchange Web Services (EWS) protocol.

1. Enable "Less Secure Apps" or generate an **App Password** in your Google Account
2. Set `GOG_ACCOUNT` to your full Google email address
3. Set `GOG_KEYRING_PASSWORD` to the generated App Password

!!! note "DE"
    Phil nutzt EWS (Exchange Web Services) für den Zugriff auf Gmail und Google Calendar.
    Du brauchst ein App-Passwort, das du in den Google-Kontoeinstellungen unter
    "Sicherheit → App-Passwörter" erstellen kannst.

---

## Step 4: Run Phil

```bash
# Terminal 1 — Backend (FastAPI)
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — Frontend (Vite dev server)
cd frontend
npm run dev
```

Open your browser at **[http://localhost:5173](http://localhost:5173)**

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'backend'`**
Run `uvicorn` from the repo root, not from inside `backend/`.

**`ChromaDB SIGBUS error`**
ChromaDB uses memory-mapped files that must not live on OneDrive or network drives.
Phil stores them at `/tmp/phil_chroma` automatically.

**Mail/calendar returns empty**
Check your `.env` credentials. Run `GET /api/mails` directly to see the raw response.

**LLM returns errors**
Verify your `ANTHROPIC_API_KEY` is valid and has remaining credits.
Phil will fall back to cloud automatically if a local LLM is configured but unavailable.
```

**Step 2: Verify**

```bash
mkdocs serve
# http://127.0.0.1:8000/setup/
# Verify: warning admonition renders, tables display correctly, code blocks copy
```

**Step 3: Commit**

```bash
git add docs/setup.md
git commit -m "docs: setup.md — local install guide, .env reference, troubleshooting"
git push origin main
```

---

## Task 7: MkDocs — prompts.md (CO-STAR)

**Files:**
- Create: `docs/prompts.md`

**Step 1: Create `docs/prompts.md`**

```markdown
# Prompts (CO-STAR Framework)

Every LLM prompt in Phil follows the **CO-STAR** framework,
a structured approach to prompt engineering:

| Letter | Stands for | Purpose |
|--------|-----------|---------|
| **C** | Context | Background information the LLM needs |
| **O** | Objective | What exactly the LLM must do |
| **S** | Style | How to communicate (structured, narrative, etc.) |
| **T** | Tone | Register and voice (professional, direct, etc.) |
| **A** | Audience | Who reads the output and what they need |
| **R** | Response | Exact output format (JSON, Markdown, plain text) |

CO-STAR prompts make LLM behaviour predictable, auditable, and easy to adjust.

---

## Prompt 1: Mail Triage (`COSTAR_PROMPT`)

Used by: `POST /api/triage-mails` and `POST /api/triage-single`

```
C (Context): Du bist ein intelligenter E-Mail-Assistent für einen Hochschuldozenten.
Du hilfst dabei, eingehende E-Mails schnell zu priorisieren.

O (Objective): Analysiere die folgende E-Mail. Bestimme Kategorie, Priorität,
erstelle eine Kurzzusammenfassung und empfehle eine konkrete Aktion.

S (Style): Strukturiert, präzise, ohne Füllwörter.

T (Tone): Professionell und sachlich.

A (Audience): Der Dozent möchte in 5 Sekunden entscheiden,
welche Mails sofortige Aufmerksamkeit brauchen.

R (Response): Antworte AUSSCHLIESSLICH mit validem JSON:
{
    "kategorie": "VIP" | "Aktion nötig" | "Nur Info" | "Ignorieren",
    "priorität": 1 | 2 | 3 | 4,
    "zusammenfassung": "Max. 2 prägnante Sätze.",
    "empfohlene_aktion": "Konkrete, sofort umsetzbare Empfehlung.",
    "stimmung": <-1.0 bis 1.0>
}
```

**Design notes:**
- The response format is strict JSON to enable reliable parsing
- `stimmung` (sentiment) is a float for programmatic colour coding, not a label
- "Ohne Füllwörter" (no filler words) in Style keeps summaries dense and actionable

---

## Prompt 2: Phil Chat System Prompt (`PHIL_SYSTEM`)

Used by: `POST /api/chat` (streaming)

```
Du bist PHIL — der smarte, proaktive persönliche Assistent.
Du bist neugierig, direkt und denkst einen Schritt voraus.

## Wie du denkst

Wenn du einen Termin, eine Mail oder Aufgabe siehst und der Kontext unklar ist:
→ Frage EINMAL kurz und gezielt nach: „Was ist [X]? Kurz recherchieren?"

Sobald du weißt, worum es geht — denke SOFORT praktisch-konkret:
  - Getränkelieferung? → Leergut bereitstellen, Zugang klären, Zahlung vorbereiten
  - Arzttermin? → Versicherungskarte, Beschwerden notiert, ggf. nüchtern kommen
  - Zoom-Call? → Link testen, Kamera/Mikro prüfen, Unterlagen griffbereit

Nicht: „Überlegen Sie sich die Ziele des Meetings" — das ist wertlos.
Ja: Die 2–4 physischen/konkreten Dinge, die wirklich zu tun sind.

## Was du tust

- Schlage proaktiv nächste Schritte vor, ohne darauf zu warten, gefragt zu werden.
- Gib eigene Einschätzung: Ist das dringend? Fehlt etwas?
- Biete konkrete Aktionen an: Antwort entwerfen, Erinnerung anlegen, Aufgabe erstellen.
- Wenn du etwas Neues lernst, merke es dir: „Ich merke mir: [Fakt]"

Antworte auf Deutsch. Prägnant, direkt, kein Bullshit.
```

**Design notes:**
- Concrete examples (Getränkelieferung, Arzttermin) prevent the LLM from giving generic advice
- The "Ich merke mir:" pattern triggers the fact-extraction pipeline
- No formal greeting instructions — Phil is direct, not corporate

---

## Prompt 3: Fact Extraction (`FACT_EXTRACTION_SYSTEM`)

Used by: background thread after each chat response

```
Extrahiere aus diesem Gespräch maximal 3 neue, konkrete Fakten über Personen,
Projekte, Konzepte, Orte oder Abläufe.
Nur wirklich neue Informationen — keine allgemeinen Aussagen.
Antworte ausschließlich mit validem JSON (kein Markdown):
[{"text": "...", "category": "Person|Projekt|Konzept|Prozedur|Ort", "confidence": 0.7}]
Wenn keine neuen Fakten: []
```

**Design notes:**
- `maximal 3` prevents fact explosion from verbose conversations
- "Nur wirklich neue Informationen" suppresses trivial extractions
- Confidence is float (not bool) to support RLHF-weighted filtering

---

## Prompt 4: Meeting Briefing (`BRIEFING_SYSTEM`)

Used by: `POST /api/briefing`

```
Du bist PHIL, der persönliche KI-Assistent.
Erstelle ein kompaktes Meeting-Briefing auf Deutsch.
Verwende EXAKT diese Markdown-Struktur, keine Abweichungen:

## 👤 Teilnehmer
<Namen aus dem Termin, oder "Keine erkannt">

## 📬 Letzte Mails
<Relevante Mails aus dem Kontext mit Datum, oder "Keine gefunden.">

## 📋 Agenda-Vorschlag
<3–5 konkrete Punkte basierend auf Termin und Mails>

Sei prägnant. Maximal 200 Wörter insgesamt. Kein Einleitungssatz.
```

**Design notes:**
- Exact Markdown structure (with emoji headings) means the frontend can render
  the output directly without parsing
- "Kein Einleitungssatz" (no introductory sentence) removes LLM throat-clearing
- 200-word limit forces the model to prioritise

---

## Adapting the Prompts

All four prompts are defined as module-level constants in `backend/main.py`.
To adapt Phil for a different domain (e.g. a medical practice instead of a university):

1. Change the **C (Context)** — update the role description
2. Change the **A (Audience)** — who reads the output and what they need
3. Adjust the **R (Response)** categories — e.g. replace "VIP / Aktion nötig / Nur Info / Ignorieren" with domain-specific categories
4. Update concrete examples in `PHIL_SYSTEM` — the examples drive behaviour more than abstract instructions

!!! note "DE — Prompts anpassen"
    Alle Prompts stehen in `backend/main.py` als Konstanten (COSTAR_PROMPT, PHIL_SYSTEM, etc.).
    Um Phil für eine andere Domäne anzupassen, ändere C (Kontext) und A (Zielgruppe)
    und passe die konkreten Beispiele im System-Prompt an.
```

**Step 2: Verify**

```bash
mkdocs serve
# http://127.0.0.1:8000/prompts/
# Verify: 4 prompt sections render, code blocks with copy buttons, table at top
```

**Step 3: Commit**

```bash
git add docs/prompts.md
git commit -m "docs: prompts.md — all 4 CO-STAR prompts with design notes"
git push origin main
```

---

## Task 8: MkDocs — architecture.md + tech-stack.md + contributing.md

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/tech-stack.md`
- Create: `docs/contributing.md`

**Step 1: Create `docs/architecture.md`**

```markdown
# Architecture

Phil is a single-service web application: a FastAPI backend that serves both
the React frontend (as static files) and a REST + SSE API.

## System overview

```
Browser
  ↓  HTTP / EventSource
FastAPI (uvicorn)
  ├── /static → React SPA (built Vite bundle)
  ├── /api/mails → exchange_helpers.py → Google Workspace (EWS)
  ├── /api/calendar → exchange_helpers.py → Google Calendar (EWS)
  ├── /api/chat (SSE) → main.py → LLM client → Anthropic / OpenAI / Local LLM
  │                              → knowledge_store.py (ChromaDB RAG)
  │                              → ontology_store.py (RDFlib graph)
  │                              → memory_store.py (SQLite + ChromaDB)
  │                              → web_search.py (DuckDuckGo)
  ├── /api/triage-mails → main.py → LLM (COSTAR_PROMPT)
  │                               → attachment_extractor.py (PDF/DOCX)
  │                               → ontology_store.py (entity indexing)
  ├── /api/briefing (SSE) → main.py → LLM (BRIEFING_SYSTEM)
  │                                 → knowledge_store.py (RAG)
  └── /api/memory/* → memory_store.py (SQLite + ChromaDB)
```

## Backend modules

| Module | Responsibility |
|--------|---------------|
| `main.py` | FastAPI app, all route handlers, prompt constants, business logic |
| `llm_client.py` | Hybrid LLM client: cloud (Anthropic/OpenAI) + local (LM Studio) with fallback |
| `exchange_helpers.py` | Google Workspace integration: mail fetch, calendar fetch |
| `knowledge_store.py` | ChromaDB vector store for email RAG |
| `ontology_store.py` | RDFlib RDF/OWL graph for entity relationships |
| `memory_store.py` | SQLite + ChromaDB dual-layer memory with RLHF |
| `attachment_extractor.py` | PDF (pdfplumber) + DOCX (python-docx) text extraction |
| `web_search.py` | DuckDuckGo search wrapper with trigger regex |

## Frontend structure

```
frontend/src/
  components/
    Views/
      Dashboard.tsx      ← main overview with event context panel
      MailsView.tsx      ← mail triage list
      CalendarView.tsx   ← calendar grid
      TasksView.tsx      ← task list
      MemoryView.tsx     ← fact browser with edit/delete
      TrainView.tsx      ← RLHF training interface
    Phil/                ← chat component with streaming
    Cards/               ← reusable mail/event cards
    Layout/              ← sidebar, nav, badges
```

## Data flow: Mail Triage

```
POST /api/triage-mails
  → exchange_helpers.fetch_google_mails()
  → For each mail:
      → attachment_extractor (if attachments)
      → LLM.create(COSTAR_PROMPT) → JSON result
      → ontology_store.index_mail_entities()
      → knowledge_store.add_mail() (ChromaDB embedding)
  → Return sorted list
```

## Data flow: Chat

```
POST /api/chat  (streaming SSE)
  → _build_context(message)
      → fetch_google_calendar() [if calendar keywords detected]
      → knowledge_store.search() [RAG — top 3 similar mails]
      → ontology_store.get_context_for_chat()
      → memory_store.search_facts() [top 5 relevant facts]
      → web_search() [if trigger regex matches]
  → LLM.stream(PHIL_SYSTEM, full_context + user_message)
  → Stream tokens to frontend via SSE
  → [background] _extract_and_store_facts()
```
```

**Step 2: Create `docs/tech-stack.md`**

```markdown
# Tech Stack

## Backend

| Library | Version | Purpose |
|---------|---------|---------|
| FastAPI | ≥0.115 | Web framework + async API |
| Uvicorn | ≥0.30 | ASGI server |
| Anthropic SDK | ≥0.40 | Claude API client |
| OpenAI SDK | ≥1.40 | OpenAI + embedding client |
| exchangelib | ≥5.1 | Google Workspace EWS client |
| python-dotenv | ≥1.0 | `.env` configuration |
| httpx | ≥0.27 | Async HTTP client |
| ChromaDB | ≥0.5 | Vector store for RAG + memory |
| pdfplumber | ≥0.11 | PDF text extraction |
| python-docx | ≥1.1 | DOCX text extraction |
| rdflib | ≥7.0 | RDF/OWL ontology graph |
| pyhafas | ≥0.6 | Deutsche Bahn Hafas API client |
| pytest | ≥8.0 | Test framework |

## Frontend

| Library | Version | Purpose |
|---------|---------|---------|
| React | 18 | UI component framework |
| TypeScript | — | Type-safe JavaScript |
| Vite | — | Build tool + dev server |
| CSS Modules | — | Scoped component styles |

## Infrastructure

| Tool | Purpose |
|------|---------|
| Docker | Container image for production deployment |
| Traefik | Reverse proxy + TLS (production) |
| GitHub Actions | CI/CD — build & deploy this site |
| GitHub Pages | Hosting for this documentation |

## External Services

| Service | Purpose |
|---------|---------|
| Anthropic Claude API | LLM for chat, triage, briefing, fact extraction |
| Google Workspace | Gmail + Calendar via EWS protocol |
| DuckDuckGo | Web search (no API key required) |
| Deutsche Bahn Hafas | Train schedule queries via PyHafas |
```

**Step 3: Create `docs/contributing.md`**

```markdown
# Contributing

Phil is an open student project. Fork it, extend it, improve it.

## Getting started

1. Fork `swrobuts/phil-knowledge-navigator` on GitHub
2. Follow the [setup guide](setup.md) to run Phil locally
3. Make your changes in a feature branch
4. Open a pull request with a clear description

## Ideas for extensions

- **Voice input** — Web Speech API in the browser, send transcript to `/api/chat`
- **Task creation from mail** — button on mail card to create a task from an action item
- **Notification push** — browser notifications for VIP mails
- **Multi-user** — session isolation so multiple people can run their own Phil
- **Local-only mode** — run entirely with a local LLM, no cloud API keys

## Code style

- Python: follow PEP 8, type hints on all functions, no bare `except`
- TypeScript: strict mode, no `any`, CSS Modules for styles
- Commits: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`)

## Licence

MIT — use it freely, credit the original where appropriate.

!!! note "DE"
    Phil ist ein offenes Studienprojekt. Forks, Extensions und Verbesserungen sind
    herzlich willkommen. Eine Pull Request mit klarer Beschreibung genügt.
```

**Step 4: Build, verify all pages**

```bash
mkdocs serve
# Check: architecture.md (code blocks render), tech-stack.md (tables), contributing.md
```

**Step 5: Commit**

```bash
git add docs/architecture.md docs/tech-stack.md docs/contributing.md
git commit -m "docs: architecture, tech-stack, contributing pages complete"
git push origin main
```

---

## Task 9: Final — screenshots + polish + deploy verification

**Step 1: Add screenshots**

- Take 3–5 screenshots of the Phil dashboard (running locally):
  - Dashboard overview
  - Mail triage list
  - Chat in action
  - Memory view
- Place them in `assets/screenshots/`
- Reference them in `index.html` below the features grid:

```html
<!-- Add below .features-grid in index.html -->
<div style="margin-top:3rem; display:grid; grid-template-columns: repeat(auto-fill, minmax(280px,1fr)); gap:1rem;">
  <img src="assets/screenshots/dashboard.png" alt="Phil Dashboard"
       style="border-radius:8px; border:1px solid var(--border); width:100%;">
  <img src="assets/screenshots/mail-triage.png" alt="Phil Mail Triage"
       style="border-radius:8px; border:1px solid var(--border); width:100%;">
  <img src="assets/screenshots/chat.png" alt="Phil Chat"
       style="border-radius:8px; border:1px solid var(--border); width:100%;">
</div>
```

**Step 2: Verify GitHub Actions deploy**

After each push, check:
- GitHub repo → Actions tab → workflow runs green
- `https://swrobuts.github.io/phil-website/` loads the landing page
- `https://swrobuts.github.io/phil-website/story/` loads the MkDocs story page

**Step 3: Final commit**

```bash
git add assets/screenshots/ index.html
git commit -m "feat: screenshots + verified GitHub Pages deploy"
git push origin main
```

---

## Summary

| Task | What gets built |
|------|----------------|
| 1 | Repo scaffold: mkdocs.yml, GitHub Actions deploy workflow |
| 2 | Landing page: hero, lineage timeline, vision, gap, features, get started, footer |
| 3 | story.md — full intellectual lineage narrative |
| 4 | use-cases.md — 1987 vs 2026 honest mapping |
| 5 | 6 feature pages (mail triage, dashboard, calendar, meeting prep, memory, RAG) |
| 6 | setup.md — local install guide, .env reference, troubleshooting |
| 7 | prompts.md — all 4 CO-STAR prompts with design notes |
| 8 | architecture.md, tech-stack.md, contributing.md |
| 9 | Screenshots + deploy verification |
