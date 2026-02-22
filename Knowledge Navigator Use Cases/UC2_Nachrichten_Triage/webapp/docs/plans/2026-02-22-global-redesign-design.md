# Global UI Redesign — PHIL PIM Dashboard
**Date:** 2026-02-22
**Scope:** Full design-system overhaul (Option B)
**Goal:** Professional Bauhaus-quality UI — clear typography, generous spacing, visual consistency across all views

---

## Problem Statement

The current UI has multiple design deficiencies:
- Category tiles are too small; numbers barely readable
- Section spacing is inconsistent and cramped
- Warm parchment background (`#F0EEE9`) feels dated
- Section headers use ALL CAPS in tiny text with low visual weight
- Task items have insufficient padding; dates shown as raw ISO strings
- Phil avatar is too small (lack of personality/presence)
- Sidebar uses Unicode characters as icons (unprofessional)
- No consistent 8px spacing grid
- Components appear misaligned at their top/bottom edges

---

## Design Principles

1. **8px grid** — All spacing values are multiples of 4px or 8px
2. **Strong hierarchy** — Three clear levels: page, section, item
3. **Restraint** — No decorative elements; every pixel serves a function
4. **Color as signal** — Category colors only for meaning, not decoration
5. **Generous whitespace** — Breathing room as a mark of quality

---

## 1. Color Tokens

### Backgrounds
| Token | Old | New | Purpose |
|---|---|---|---|
| `--content-bg` | `#F0EEE9` (warm parchment) | `#F7F8FA` (cool light gray) | Main content area |
| `--card-bg` | `#FFFFFF` | `#FFFFFF` | Cards, panels |
| `--sidebar-bg` | `#FFFFFF` | `#FFFFFF` | Sidebar |

### Brand
| Token | Value | Purpose |
|---|---|---|
| `--brand` | `#1B3A6B` | Primary blue (unchanged) |
| `--brand-dark` | `#112B52` | Hover state |
| `--brand-light` | `#EBF1FC` | Active sidebar bg, subtle tints |

### Category Accents (refined for contrast)
| Category | Background | Text | Badge |
|---|---|---|---|
| VIP | `#FFF0F0` | `#991B1B` | `#C41A1A` |
| Aktion | `#FFFBF0` | `#92400E` | `#C47A00` |
| Info | `#F0F5FF` | `#1D4ED8` | `#1D4ED8` |
| Ignorieren | `#F8F9FA` | `#64748B` | `#94A3B8` |

### Borders & Shadows
| Token | Value |
|---|---|
| `--border` | `#E4E7EB` |
| `--border-light` | `#F0F2F5` |
| `--shadow-sm` | `0 1px 3px rgba(0,0,0,.06)` |
| `--shadow-md` | `0 4px 16px rgba(0,0,0,.08)` |
| `--shadow-lg` | `0 8px 32px rgba(0,0,0,.12)` |

---

## 2. Typography

**Font:** DM Sans (unchanged — geometric, Bauhaus-appropriate)

### Scale
| Token | Size | Usage |
|---|---|---|
| `--text-xs` | `0.6875rem` (11px) | Metadata, timestamps |
| `--text-sm` | `0.8125rem` (13px) | Secondary labels |
| `--text-base` | `0.9375rem` (15px) | Body text |
| `--text-lg` | `1.0625rem` (17px) | Card titles |
| `--text-xl` | `1.25rem` (20px) | Section headings |
| `--text-2xl` | `1.5rem` (24px) | Page headings |
| `--text-3xl` | `2rem` (32px) | Tile numbers (new) |
| `--text-4xl` | `3rem` (48px) | Hero tile numbers (new) |

### Rules
- Section headers: sentence case (not ALL CAPS), `--text-xl`, `font-weight: 600`
- Tile labels: `--text-xs`, `letter-spacing: 0.08em`, uppercase, `opacity: 0.55`
- Tile numbers: `--text-4xl`, `font-weight: 800`
- Dates in task list: formatted as `So, 22. Feb` (not raw ISO)
- Sidebar nav items: `--text-sm`, `font-weight: 500`

---

## 3. Spacing (8px Grid)

```
4px  — tight internal gaps (icon + label)
8px  — small padding, badge padding
12px — medium padding
16px — standard card padding
24px — section padding
32px — section gap
48px — large section separation
```

---

## 4. Component Designs

### 4.1 Dashboard — Category Tiles
```
┌──────────────────────────────────────┐
│                              [count] │  ← 3rem bold, right-aligned
│                                      │
│  VIP                                 │  ← 11px uppercase label, bottom
└──────────────────────────────────────┘
   ▲ 4px colored left border
   Height: 96px minimum
   Padding: 16px 20px
```
- Four tiles in a row, equal width
- On click: navigates to filtered mail view

### 4.2 Dashboard — Tagesplan (empty state)
- Centered icon + message: `Keine Termine heute` with date
- Remove excessive height: max-height capped, overflow hidden
- Empty state uses `--text-sm` in `--text-secondary`

### 4.3 Task Items
```
┌────────────────────────────────────────────┐
│  ●  Bachelorarbeit korrigieren    So 22 Feb │
└────────────────────────────────────────────┘
   Padding: 12px 16px
   Min-height: 52px
   Separator: 1px #F0F2F5
   Dot: 10px, color = priority level
```

### 4.4 Phil Panel
- Avatar: `96px` × `96px` (was ~40px), centered with `box-shadow`
- Panel width: `400px` (was `340px`)
- Message bubbles: `padding: 12px 16px`, `gap: 16px` between messages
- Input area: more prominent, full-width, taller

### 4.5 Sidebar
- Active state: full-row colored block `--brand-light` with `3px` brand-colored left border
- Nav item height: `44px`
- Replace Unicode icons with inline SVG (Dashboard, Mail, Calendar, Tasks, Train)
- Brand area: larger PHIL text, subtitle underneath

### 4.6 Header / Topbar
- Clear zone separation: date/time | next event | status badges
- Status badges (Cloud, Exchange): consistent pill style, `--text-xs`

---

## 5. Files to Change

| File | Change Type |
|---|---|
| `src/styles/tokens.css` | New color, spacing, type tokens |
| `src/components/Layout/AppShell.module.css` | Header zones, grid |
| `src/components/Layout/Sidebar.module.css` | Nav items, active state, SVG icons |
| `src/components/Views/Dashboard.module.css` | Tiles, schedule, tasks, context panel |
| `src/components/Views/TasksView.module.css` | Task item spacing |
| `src/components/Views/CalendarView.module.css` | Consistent card/border styling |
| `src/components/Views/MailsView.module.css` | Consistent card/border styling |
| `src/components/Phil/PhilPanel.module.css` | Avatar size, message spacing |
| `src/components/Cards/MailCard.module.css` | Badge refinements |
| `src/components/Login/Login.module.css` | Minor token alignment |
| `src/components/Layout/Sidebar.tsx` | SVG icon components (inline) |
| `src/components/Phil/PhilPanel.tsx` | Avatar size attribute |
| `src/components/Views/Dashboard.tsx` | Date formatting for tasks |

---

## 6. Out of Scope

- No changes to routing, API, or business logic
- No changes to color coding semantics (VIP=red, Aktion=amber, Info=blue)
- No mobile layout changes (handled separately)
- No dark mode

---

## Success Criteria

- Screenshot comparison shows clear quality improvement
- All section borders/edges align on a consistent grid
- Phil avatar visible and prominent
- No Unicode icons in sidebar
- Tile numbers readable at a glance from normal viewing distance
- Task dates human-readable
- No cramped areas — every component has adequate breathing room
