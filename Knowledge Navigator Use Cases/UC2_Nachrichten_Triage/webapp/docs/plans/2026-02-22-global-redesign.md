# Global UI Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the entire visual layer with a professional Bauhaus-quality design system — clean typography, generous whitespace, aligned grid, consistent component language throughout all views.

**Architecture:** CSS-only redesign (Option B) — rewrite `tokens.css` as the single source of truth, then update all CSS Modules to consume the new tokens. Minimal TSX changes only where structure must change (Phil avatar size, sidebar SVG icons, task date formatting). No business logic touched.

**Tech Stack:** React + TypeScript, CSS Modules, DM Sans font, Vite dev server, app running live at `http://localhost:8001` (uvicorn), Playwright browser available for visual verification.

---

## Pre-flight

The app is already running at `http://localhost:8001`. After each task, open the browser and take a screenshot to verify. The frontend uses Vite — but since we're running via uvicorn (static build), changes require a rebuild. Use this command after each task:

```bash
cd /Users/robert/Library/CloudStorage/OneDrive-Persönlich/Vorlesungen/Datenbasierte Fallstudien/Knowledge\ Navigator\ Use\ Cases/UC2_Nachrichten_Triage/webapp
npm --prefix frontend run build && echo "BUILD OK"
```

Then kill and restart uvicorn:
```bash
pkill -f "uvicorn backend.main" && sleep 1
uvicorn backend.main:app --host 0.0.0.0 --port 8001 &
sleep 2 && curl -s -o /dev/null -w "%{http_code}" http://localhost:8001
```

---

## Task 1: Design Tokens — Foundation

**Files:**
- Modify: `frontend/src/styles/tokens.css`

**Step 1: Read the current tokens file**
```
Read: frontend/src/styles/tokens.css
```
Note all existing variable names — we must keep names identical so all CSS Modules continue to work.

**Step 2: Replace the file with the new token set**

```css
/* ── PHIL PIM Dashboard — Design Tokens v2 ─────────────────────────────── */
/* 8-point grid. All spacing is a multiple of 4px or 8px. */

:root {
  /* ── Fonts ─────────────────────────────────────────────────────────────── */
  --font:      'DM Sans', system-ui, -apple-system, sans-serif;
  --font-mono: 'DM Mono', 'Fira Mono', monospace;

  /* ── Type Scale ─────────────────────────────────────────────────────────── */
  --text-xs:   0.6875rem;   /* 11px — badges, captions, tile labels */
  --text-sm:   0.8125rem;   /* 13px — secondary text, sidebar nav */
  --text-base: 0.9375rem;   /* 15px — body copy */
  --text-lg:   1.0625rem;   /* 17px — card titles */
  --text-xl:   1.25rem;     /* 20px — section headings */
  --text-2xl:  1.5rem;      /* 24px — page headings */
  --text-3xl:  2rem;        /* 32px — tile numbers */
  --text-4xl:  2.75rem;     /* 44px — hero tile numbers */

  /* ── Brand (Prussian Blue) ──────────────────────────────────────────────── */
  --amber:       #1B3A6B;
  --amber-dark:  #112B52;
  --amber-light: #EBF1FC;

  /* ── Backgrounds ────────────────────────────────────────────────────────── */
  --content-bg:     #F7F8FA;   /* Cool light gray — main content area */
  --content-border: #E4E7EB;

  /* ── Cards & Surfaces ───────────────────────────────────────────────────── */
  --card-bg:           #FFFFFF;
  --card-border:       #E4E7EB;
  --card-shadow:       0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  --card-shadow-hover: 0 4px 16px rgba(0,0,0,.10), 0 2px 4px rgba(0,0,0,.06);

  /* ── Sidebar ────────────────────────────────────────────────────────────── */
  --sidebar-bg:          #FFFFFF;
  --sidebar-border:      #E4E7EB;
  --sidebar-text:        #4B5563;
  --sidebar-text-active: #1B3A6B;
  --sidebar-hover:       #F7F8FA;
  --sidebar-active:      #EBF1FC;
  --sidebar-accent:      #1B3A6B;

  /* ── Phil Panel ─────────────────────────────────────────────────────────── */
  --phil-bg:     #FFFFFF;
  --phil-border: #E4E7EB;

  /* ── Category — VIP ─────────────────────────────────────────────────────── */
  --vip-bg:     #FFF0F0;
  --vip-text:   #991B1B;
  --vip-badge:  #C41A1A;

  /* ── Category — Aktion ──────────────────────────────────────────────────── */
  --aktion-bg:     #FFFBF0;
  --aktion-text:   #92400E;
  --aktion-badge:  #C47A00;

  /* ── Category — Info ────────────────────────────────────────────────────── */
  --info-bg:     #F0F5FF;
  --info-text:   #1D4ED8;
  --info-badge:  #1D4ED8;

  /* ── Category — Ignorieren ──────────────────────────────────────────────── */
  --ignorieren-bg:     #F8F9FA;
  --ignorieren-text:   #64748B;
  --ignorieren-badge:  #94A3B8;

  /* ── Text Colors ────────────────────────────────────────────────────────── */
  --text-primary:   #111827;
  --text-secondary: #6B7280;
  --text-tertiary:  #9CA3AF;

  /* ── Semantic ───────────────────────────────────────────────────────────── */
  --success:  #059669;
  --error:    #DC2626;
  --warning:  #D97706;

  /* ── Borders ────────────────────────────────────────────────────────────── */
  --border:       #E4E7EB;
  --border-light: #F0F2F5;

  /* ── Shadows ────────────────────────────────────────────────────────────── */
  --shadow-sm: 0 1px 3px rgba(0,0,0,.06);
  --shadow-md: 0 4px 16px rgba(0,0,0,.08);
  --shadow-lg: 0 8px 32px rgba(0,0,0,.12);

  /* ── Radii ──────────────────────────────────────────────────────────────── */
  --radius-sm: 4px;
  --radius:    6px;
  --radius-lg: 10px;
  --radius-xl: 16px;

  /* ── Layout ─────────────────────────────────────────────────────────────── */
  --sidebar-w:    240px;
  --sidebar-mini: 52px;
  --header-h:     52px;
  --phil-w:       400px;
  --bottom-nav-h: 58px;

  /* ── Spacing (8pt grid) ─────────────────────────────────────────────────── */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;

  /* ── Motion ─────────────────────────────────────────────────────────────── */
  --transition: 150ms cubic-bezier(.4, 0, .2, 1);
}
```

**Step 3: Build & verify**
```bash
cd .../webapp && npm --prefix frontend run build && echo "BUILD OK"
```
Expected: `BUILD OK` with no TypeScript errors.

**Step 4: Commit**
```bash
git add frontend/src/styles/tokens.css
git commit -m "design: new token system — cool bg, 8pt grid, richer type scale"
```

---

## Task 2: Sidebar — SVG Icons & Active State

**Files:**
- Modify: `frontend/src/components/Layout/Sidebar.tsx`
- Modify: `frontend/src/components/Layout/Sidebar.module.css`

**Step 1: Read both files**
```
Read: frontend/src/components/Layout/Sidebar.tsx
Read: frontend/src/components/Layout/Sidebar.module.css
```

**Step 2: Replace Unicode icons with inline SVG in Sidebar.tsx**

Find the nav items section. Replace each Unicode character icon with a clean inline SVG.
Use these exact SVGs (16×16 viewBox, stroke-based, no fill):

```tsx
// Add these icon components at the top of Sidebar.tsx (above the main component):

const IconDashboard = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <rect x="1" y="1" width="6" height="6" rx="1"/>
    <rect x="9" y="1" width="6" height="6" rx="1"/>
    <rect x="1" y="9" width="6" height="6" rx="1"/>
    <rect x="9" y="9" width="6" height="6" rx="1"/>
  </svg>
);

const IconMail = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="1" y="3" width="14" height="10" rx="1.5"/>
    <path d="M1 5l7 5 7-5"/>
  </svg>
);

const IconCalendar = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <rect x="1" y="2.5" width="14" height="12" rx="1.5"/>
    <path d="M1 6.5h14"/>
    <path d="M5 1v3M11 1v3"/>
  </svg>
);

const IconTasks = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <path d="M2 4h12M2 8h8M2 12h10"/>
    <circle cx="13" cy="11.5" r="2" fill="none"/>
    <path d="M12 11.5l.8.8 1.6-1.6"/>
  </svg>
);

const IconTrain = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="1" width="10" height="11" rx="2"/>
    <path d="M3 7h10"/>
    <circle cx="5.5" cy="9.5" r="1" fill="currentColor" stroke="none"/>
    <circle cx="10.5" cy="9.5" r="1" fill="currentColor" stroke="none"/>
    <path d="M5 12l-2 3M11 12l2 3"/>
  </svg>
);
```

Replace the nav item rendering to use these components instead of the Unicode strings.

**Step 3: Rewrite Sidebar.module.css**

```css
/* Sidebar.module.css */

.sidebar {
  width: var(--sidebar-w);
  min-width: var(--sidebar-w);
  height: 100%;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  transition: width var(--transition), min-width var(--transition);
  overflow: hidden;
}
.sidebar.mini {
  width: var(--sidebar-mini);
  min-width: var(--sidebar-mini);
}

/* Brand */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 16px 16px;
  border-bottom: 1px solid var(--border-light);
}
.brandTitle {
  font-size: var(--text-xl);
  font-weight: 800;
  color: var(--amber);
  letter-spacing: -0.02em;
  white-space: nowrap;
}
.brandSub {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
  margin-top: 1px;
}

/* Nav */
.nav {
  flex: 1;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.navItem {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  height: 44px;
  border-radius: var(--radius);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--sidebar-text);
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  width: 100%;
  white-space: nowrap;
  transition: background var(--transition), color var(--transition);
  position: relative;
}
.navItem:hover {
  background: var(--sidebar-hover);
  color: var(--text-primary);
}
.navItem.active {
  background: var(--sidebar-active);
  color: var(--sidebar-text-active);
  font-weight: 600;
}
.navItem.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 3px;
  background: var(--amber);
  border-radius: 0 2px 2px 0;
}

.navIcon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  opacity: 0.7;
}
.navItem.active .navIcon,
.navItem:hover .navIcon {
  opacity: 1;
}

.navLabel { flex: 1; }

.badge {
  background: var(--amber);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  min-width: 18px;
  text-align: center;
}

/* Footer */
.footer {
  padding: 12px 8px;
  border-top: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.user {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 8px;
}
.logoutBtn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius);
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  flex-shrink: 0;
  transition: background var(--transition), color var(--transition);
}
.logoutBtn:hover {
  background: var(--border-light);
  color: var(--error);
}

/* Toggle button */
.toggleBtn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  flex-shrink: 0;
  transition: var(--transition);
}
.toggleBtn:hover { background: var(--sidebar-hover); }

@media (max-width: 899px) {
  .sidebar { display: none; }
}
```

**Step 4: Build & screenshot**
```bash
npm --prefix frontend run build && echo "BUILD OK"
```
Reload browser. Sidebar should have clean icons, proper active state.

**Step 5: Commit**
```bash
git add frontend/src/components/Layout/Sidebar.tsx frontend/src/components/Layout/Sidebar.module.css
git commit -m "design: sidebar — SVG icons, 44px nav items, active border accent"
```

---

## Task 3: Dashboard — Category Tiles

**Files:**
- Modify: `frontend/src/components/Views/Dashboard.module.css`
- Modify: `frontend/src/components/Views/Dashboard.tsx` (tile markup only)

**Step 1: Read both files**
```
Read: frontend/src/components/Views/Dashboard.module.css
Read: frontend/src/components/Views/Dashboard.tsx
```

**Step 2: Find the tile section in Dashboard.tsx**

Locate the 4 category tiles (VIP, Aktion, Info, Ignorieren). The tile button currently renders label + count in a compact layout. Change it to put the count prominently on top and the label below:

```tsx
// Current structure (approximately):
<button className={...}>
  <span>{label}</span>
  <span>{count}</span>
</button>

// New structure:
<button className={`${styles.tile} ${styles[category]}`} onClick={...}>
  <div className={styles.tileCount}>{count}</div>
  <div className={styles.tileLabel}>{label}</div>
</button>
```

Make sure to remove `.tileMain`, `.tileHeader`, `.tileBar`, `.tileBarFill` usages from the tile buttons if they exist — replace with the simpler structure above.

**Step 3: Rewrite the tile CSS section in Dashboard.module.css**

Find and replace the `.tilesRow`, `.tile`, `.tileMain`, `.tileCount`, `.tileLabel`, `.tileBar`, `.tileBarFill` rules:

```css
/* ── Category Tiles ─────────────────────────────────────────────── */
.tilesRow {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
@media (max-width: 700px) {
  .tilesRow { grid-template-columns: repeat(2, 1fr); }
}

.tile {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--radius-lg);
  padding: 20px 24px 18px;
  cursor: pointer;
  text-align: left;
  position: relative;
  overflow: hidden;
  transition: box-shadow var(--transition), transform var(--transition);
  box-shadow: var(--card-shadow);
  min-height: 100px;
  border-left-width: 4px;
}
.tile:hover {
  box-shadow: var(--card-shadow-hover);
  transform: translateY(-2px);
}

.tileCount {
  font-size: var(--text-4xl);
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.03em;
  font-family: var(--font);
  color: var(--text-primary);
  display: block;
  margin-bottom: 8px;
}
.tileLabel {
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

/* Category colors — border-left accent + count color */
.vip.tile  { border-left-color: var(--vip-badge); }
.aktion.tile { border-left-color: var(--aktion-badge); }
.info.tile   { border-left-color: var(--info-badge); }
.ignorieren.tile { border-left-color: var(--ignorieren-badge); }

.vip    .tileCount { color: var(--vip-badge); }
.aktion .tileCount { color: var(--aktion-badge); }
.info   .tileCount { color: var(--info-badge); }
.ignorieren .tileCount { color: var(--ignorieren-badge); }

.tileSpinner { font-size: .9rem; opacity: .5; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
```

**Step 4: Build & verify**
```bash
npm --prefix frontend run build && echo "BUILD OK"
```
Reload browser — tiles should be tall, large numbers, colored left borders.

**Step 5: Commit**
```bash
git add frontend/src/components/Views/Dashboard.module.css frontend/src/components/Views/Dashboard.tsx
git commit -m "design: dashboard tiles — 100px height, 44px numbers, colored left border"
```

---

## Task 4: Dashboard — Section Headers, Schedule & Tasks

**Files:**
- Modify: `frontend/src/components/Views/Dashboard.module.css`
- Modify: `frontend/src/components/Views/Dashboard.tsx` (date formatting only)

**Step 1: Read current dashboard CSS (already read in Task 3)**

**Step 2: Update section header styles in Dashboard.module.css**

Find and replace `.sectionTitle`, `.sectionHeader`, `.panelTitle` (or equivalent heading styles):

```css
/* ── Section Headers ────────────────────────────────────────────── */
.sectionTitle,
.panelTitle {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  margin: 0;
}

.sectionHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}

/* ── Dashboard grid ─────────────────────────────────────────────── */
.dashGrid {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 899px) {
  .dashGrid { grid-template-columns: 1fr; }
}
```

**Step 3: Update task item styles in Dashboard.module.css**

Find `.taskItem`, `.taskList`, `.taskTitle`, `.taskDate` (or equivalent):

```css
/* ── Task List ──────────────────────────────────────────────────── */
.taskList {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.taskItem {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light);
  background: var(--card-bg);
  transition: background var(--transition);
  cursor: pointer;
}
.taskItem:first-child { border-radius: var(--radius) var(--radius) 0 0; }
.taskItem:last-child  { border-bottom: none; border-radius: 0 0 var(--radius) var(--radius); }
.taskItem:only-child  { border-radius: var(--radius); border-bottom: none; }
.taskItem:hover { background: var(--content-bg); }

.taskDot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--amber);
}
.taskDot.high    { background: var(--vip-badge); }
.taskDot.normal  { background: var(--info-badge); }
.taskDot.low     { background: var(--ignorieren-badge); }

.taskBody { flex: 1; min-width: 0; }
.taskTitle {
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.taskDate {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: 2px;
}

.taskActions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity var(--transition);
}
.taskItem:hover .taskActions { opacity: 1; }

.taskActionBtn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--card-bg);
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: var(--transition);
}
.taskActionBtn:hover { background: var(--border-light); }
```

**Step 4: Format task dates in Dashboard.tsx**

Find where task `.due_date` (or equivalent date field) is rendered. Replace raw date string with formatted version:

```tsx
// Helper function — add near top of Dashboard.tsx:
function formatDate(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' });
  // Output: "So, 22. Feb"
}

// In the JSX, replace: {task.due_date}
// With:               {formatDate(task.due_date)}
```

**Step 5: Build & verify**
```bash
npm --prefix frontend run build && echo "BUILD OK"
```
Tasks should show `So, 22. Feb` style dates with proper padding.

**Step 6: Commit**
```bash
git add frontend/src/components/Views/Dashboard.module.css frontend/src/components/Views/Dashboard.tsx
git commit -m "design: dashboard sections — proper headers, 52px task items, human dates"
```

---

## Task 5: Phil Panel — Avatar & Message Spacing

**Files:**
- Modify: `frontend/src/components/Phil/PhilPanel.module.css`
- Modify: `frontend/src/components/Phil/PhilPanel.tsx` (avatar size only)

**Step 1: Read both files**
```
Read: frontend/src/components/Phil/PhilPanel.module.css
Read: frontend/src/components/Phil/PhilPanel.tsx
```

**Step 2: Update avatar in PhilPanel.tsx**

Find the `<img>` tag for the Phil avatar. Change its width/height to 96px:
```tsx
// Find: <img src={...} alt="PHIL" style={{...}} />
// Ensure it has: width={96} height={96}  (or className with new CSS)
// Also ensure the container centers it
```

**Step 3: Rewrite PhilPanel.module.css key sections**

Find and replace the panel header, avatar, messages, and input sections:

```css
/* Panel container */
.panel {
  width: var(--phil-w);
  min-width: var(--phil-w);
  height: 100%;
  background: var(--phil-bg);
  border-left: 1px solid var(--phil-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
.panelHeader {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}

/* Avatar */
.avatar {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  object-fit: cover;
  box-shadow: 0 2px 12px rgba(27,58,107,.15);
  flex-shrink: 0;
}

/* When avatar is in its own centered row (header variant) */
.avatarRow {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 20px 16px;
  border-bottom: 1px solid var(--border-light);
  gap: 10px;
  flex-shrink: 0;
}
.avatarRow .avatar { width: 80px; height: 80px; }
.avatarName {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--amber);
  letter-spacing: 0.04em;
}

/* Quick actions */
.quickActions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}
.quickBtn {
  font-size: var(--text-xs);
  font-weight: 500;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
  transition: var(--transition);
}
.quickBtn:hover {
  background: var(--amber-light);
  border-color: var(--amber);
  color: var(--amber);
}

/* Messages */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  scroll-behavior: smooth;
}

.messageBubble {
  max-width: 88%;
  padding: 12px 16px;
  border-radius: var(--radius-lg);
  font-size: var(--text-base);
  line-height: 1.55;
}
.messageBubble.phil {
  background: var(--content-bg);
  color: var(--text-primary);
  align-self: flex-start;
  border-bottom-left-radius: 4px;
}
.messageBubble.user {
  background: var(--amber);
  color: #fff;
  align-self: flex-end;
  border-bottom-right-radius: 4px;
}

/* Input */
.inputRow {
  display: flex;
  gap: 8px;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--border-light);
  flex-shrink: 0;
}
.chatInput {
  flex: 1;
  padding: 10px 14px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  font-size: var(--text-base);
  font-family: var(--font);
  background: var(--content-bg);
  color: var(--text-primary);
  outline: none;
  transition: border-color var(--transition);
  resize: none;
}
.chatInput:focus { border-color: var(--amber); background: var(--card-bg); }
.sendBtn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius);
  border: none;
  background: var(--amber);
  color: #fff;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background var(--transition);
}
.sendBtn:hover { background: var(--amber-dark); }
.sendBtn:disabled { opacity: .4; cursor: not-allowed; }
```

**Step 4: Build & verify**
```bash
npm --prefix frontend run build && echo "BUILD OK"
```
Phil avatar should now be large and prominent. Messages should have generous spacing.

**Step 5: Commit**
```bash
git add frontend/src/components/Phil/PhilPanel.module.css frontend/src/components/Phil/PhilPanel.tsx
git commit -m "design: phil panel — 96px avatar, generous message spacing, 400px width"
```

---

## Task 6: AppShell Header

**Files:**
- Modify: `frontend/src/components/Layout/AppShell.module.css`

**Step 1: Read the file**
```
Read: frontend/src/components/Layout/AppShell.module.css
```

**Step 2: Rewrite header/topbar styles**

Find the `.topbar`, `.header`, and badge-related rules. Update:

```css
/* ── App Shell ─────────────────────────────────────────────────── */
.shell {
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-rows: var(--header-h) 1fr;
  height: 100dvh;
  overflow: hidden;
  background: var(--content-bg);
}

/* Topbar */
.topbar {
  grid-column: 1 / -1;
  height: var(--header-h);
  background: var(--card-bg);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 16px;
  z-index: 10;
}

.topbarDate {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}
.topbarTime {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-left: 6px;
}

.topbarSpacer { flex: 1; }

/* Next event chip */
.nextEvent {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-radius: 999px;
  background: var(--amber-light);
  border: 1px solid rgba(27,58,107,.15);
  font-size: var(--text-xs);
  color: var(--amber);
  font-weight: 500;
  white-space: nowrap;
  max-width: 340px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nextEventTime {
  font-weight: 700;
  flex-shrink: 0;
}

/* Status badges */
.statusGroup {
  display: flex;
  align-items: center;
  gap: 8px;
}
.statusBadge {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: 500;
  white-space: nowrap;
}
.statusDot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
  flex-shrink: 0;
}
.statusDot.warning { background: var(--warning); }
.statusDot.error   { background: var(--error); }

/* LLM badge */
.llmBadge {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--amber-light);
  font-size: var(--text-xs);
  color: var(--amber);
  font-weight: 600;
}
```

**Step 3: Build & verify**
```bash
npm --prefix frontend run build && echo "BUILD OK"
```
Header should be clean and zoned.

**Step 4: Commit**
```bash
git add frontend/src/components/Layout/AppShell.module.css
git commit -m "design: appshell header — clean zones, consistent status badges"
```

---

## Task 7: Mail Cards & Views Polish

**Files:**
- Modify: `frontend/src/components/Cards/MailCard.module.css`
- Modify: `frontend/src/components/Views/MailsView.module.css`
- Modify: `frontend/src/components/Views/CalendarView.module.css`
- Modify: `frontend/src/components/Views/TasksView.module.css`

**Step 1: Read all four files**

**Step 2: In MailCard.module.css** — update card padding and badge styles:

Find card rules and ensure:
```css
.card {
  padding: 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--card-shadow);
  transition: box-shadow var(--transition), transform var(--transition);
  cursor: pointer;
}
.card:hover {
  box-shadow: var(--card-shadow-hover);
  transform: translateY(-1px);
}
/* Ensure category left border on cards mirrors tiles */
.card.vip        { border-left: 3px solid var(--vip-badge); }
.card.aktion     { border-left: 3px solid var(--aktion-badge); }
.card.info       { border-left: 3px solid var(--info-badge); }
.card.ignorieren { border-left: 3px solid var(--ignorieren-badge); }
```

**Step 3: In MailsView.module.css** — update toolbar and list spacing:
```css
.toolbar {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.mailList {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
```

**Step 4: In TasksView.module.css** — ensure task table rows have proper height:
```css
.taskRow {
  padding: 12px 16px;
  min-height: 52px;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  gap: 12px;
}
```

**Step 5: In CalendarView.module.css** — ensure consistent border/radius tokens are used (replace hardcoded values with token references where found).

**Step 6: Build & verify**
```bash
npm --prefix frontend run build && echo "BUILD OK"
```
Navigate to Mails and Tasks views in the browser to verify.

**Step 7: Commit**
```bash
git add frontend/src/components/Cards/MailCard.module.css
git add frontend/src/components/Views/MailsView.module.css
git add frontend/src/components/Views/CalendarView.module.css
git add frontend/src/components/Views/TasksView.module.css
git commit -m "design: mail cards and views — consistent padding, border accents, spacing"
```

---

## Task 8: Login Screen Polish

**Files:**
- Modify: `frontend/src/components/Login/Login.module.css`

**Step 1: Read the file**
```
Read: frontend/src/components/Login/Login.module.css
```

**Step 2: Update the login card**

The login screen already looks reasonable. Apply token consistency:
```css
.loginCard {
  background: var(--card-bg);
  border-radius: var(--radius-xl);
  padding: 40px 36px;
  width: 100%;
  max-width: 400px;
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.input {
  width: 100%;
  padding: 10px 14px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  font-size: var(--text-base);
  font-family: var(--font);
  background: var(--content-bg);
  color: var(--text-primary);
  outline: none;
  transition: border-color var(--transition), background var(--transition);
}
.input:focus { border-color: var(--amber); background: var(--card-bg); }

.submitBtn {
  width: 100%;
  padding: 12px;
  background: var(--amber);
  color: #fff;
  border: none;
  border-radius: var(--radius);
  font-size: var(--text-base);
  font-weight: 600;
  cursor: pointer;
  font-family: var(--font);
  transition: background var(--transition);
}
.submitBtn:hover { background: var(--amber-dark); }
```

**Step 3: Build & final verification**
```bash
npm --prefix frontend run build && echo "BUILD OK"
```
Take a full-page screenshot. Compare with the original.

**Step 4: Final commit**
```bash
git add frontend/src/components/Login/Login.module.css
git commit -m "design: login — token alignment, consistent input/button styling"
```

---

## Task 9: Final Integration Check

**Step 1: Rebuild and restart**
```bash
npm --prefix frontend run build && echo "BUILD OK"
pkill -f "uvicorn backend.main" && sleep 1
uvicorn backend.main:app --host 0.0.0.0 --port 8001 &
sleep 3
```

**Step 2: Screenshot all views**
Using Playwright:
1. Login screen
2. Dashboard
3. Mails view
4. Calendar view
5. Tasks view
6. Phil panel open

**Step 3: Check alignment**
Verify:
- [ ] Tile numbers are large and readable
- [ ] Section headers are sentence-case, semibold, visible
- [ ] Task dates show `So, 22. Feb` format
- [ ] Sidebar has SVG icons, active state visible
- [ ] Phil avatar is large (96px)
- [ ] No raw `#F0EEE9` parchment tone — cool gray throughout
- [ ] All borders align on consistent grid
- [ ] No ALL CAPS section headers remain

**Step 4: Final commit**
```bash
git add -A
git commit -m "design: complete global Bauhaus redesign — consistent, professional UI"
```
