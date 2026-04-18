# Mini Orchestrator — Design System

**Version**: 1.0  
**Last updated**: 2026-04-16

---

## 1. Design Principles

1. **Metallic, not flat** — surfaces feel slightly luminous; muted golds and jewel tones signal state and role.
2. **Dark-first** — the default theme is dark; light mode is a supported inversion, not an afterthought.
3. **Role identity** — every agent role has a persistent color. A user should recognize PRD (tan), Backend (teal), Security (rose) without reading the label.
4. **Minimal chrome** — no borders for decoration, no shadows by default in dark mode. Space and contrast carry the hierarchy.
5. **Information-dense, not cluttered** — cards are compact; only critical state is surfaced inline. Details live in modals.

---

## 2. Color Palette

### Design Tokens (constant across themes)

```css
--gold-active: #d4af37    /* active gold — CTA labels, brief badge */
--gold-light:  #e8c87a    /* softer gold — human task accent */

/* Role identity colors */
--backend:      #5aada0   /* teal */
--frontend:     #c4907a   /* terracotta */
--architecture: #8a80b8   /* slate purple */
--security:     #b87a8a   /* dusty rose */
--devops:       #9b8ec4   /* lavender */
--test:         #68a8d4   /* sky blue */
--prd:          #a0988a   /* warm stone */
--review:       #a898c4   /* soft violet */
--human:        #e8c87a   /* gold */
```

### Dark Theme (default)

```css
--bg-primary:      #16141a   /* page background */
--bg-panel:        #1e1c25   /* side panel, modals */
--bg-card:         #252330   /* task card background */
--bg-card-hover:   #2e2c38
--bg-sprint-row:   #2a2838   /* wave/sprint row background */
--bg-tint-error:   #332828   /* error state card tint */
--bg-tint-blocked: #332e28   /* blocked state card tint */

--border:          #2a2830
--border-soft:     #3a3845

--text-primary:    #e5e0d5
--text-secondary:  #8a8680
--text-muted:      #6a6660

--shadow-glow: 0 4px 16px rgba(212, 175, 55, 0.08)
--shadow-card: none
--shadow-board: none

--prose-code-bg: #2a2830
--prose-code-fg: #e8c87a

/* Role badge tints (dark) */
--type-backend-bg:      #122525    --type-backend-fg:      #6dbfb0
--type-frontend-bg:     #251a1e    --type-frontend-fg:     #c4907a
--type-architecture-bg: #1a1a28    --type-architecture-fg: #8a80b8
--type-security-bg:     #251a20    --type-security-fg:     #b87a8a
--type-devops-bg:       #1a1a28    --type-devops-fg:       #9b8ec4
--type-test-bg:         #121e2a    --type-test-fg:         #68a8d4
--type-human-bg:        #25201a    --type-human-fg:        #e8c87a
--type-prd-bg:          #201e1a    --type-prd-fg:          #a0988a
--type-review-bg:       #1e1a28    --type-review-fg:       #a898c4
```

### Light Theme

```css
--bg-primary:      #f5f2eb
--bg-panel:        #fdfbf5
--bg-card:         #ffffff
--bg-card-hover:   #faf7f0
--bg-sprint-row:   #f5f0e8
--bg-tint-error:   #fff0f0
--bg-tint-blocked: #fff8f0

--border:          #e5e0d5
--border-soft:     #d5cfc0

--text-primary:    #2a2520
--text-secondary:  #5a544a
--text-muted:      #a09a8a

--shadow-glow: 0 4px 16px rgba(80, 60, 30, 0.08)
--shadow-card: 0 1px 3px rgba(80, 60, 30, 0.04)
--shadow-board: 0 4px 24px rgba(80, 60, 30, 0.04)

--prose-code-bg: #f0ebe0
--prose-code-fg: #6a4a1a

/* Role badge tints (light) — pastel bg + darker fg */
--type-backend-bg:      #e0f2ec    --type-backend-fg:      #2a7a6a
--type-frontend-bg:     #f5e5e0    --type-frontend-fg:     #9a6050
--type-architecture-bg: #e8e0f5    --type-architecture-fg: #5a4a88
--type-security-bg:     #f5e0e8    --type-security-fg:     #8a5a6a
--type-devops-bg:       #ede5f5    --type-devops-fg:       #6a5a98
--type-test-bg:         #e0eef5    --type-test-fg:         #3a7098
--type-human-bg:        #fff0d0    --type-human-fg:        #9a7a20
--type-prd-bg:          #edeae0    --type-prd-fg:          #6a6458
--type-review-bg:       #ede0f5    --type-review-fg:       #7a5aa0
```

Theme is toggled via `data-theme` attribute on `<html>`. Persisted in `localStorage`.

---

## 3. Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Body | DM Sans, system-ui, sans-serif | 14px | 400 |
| Page title (`h1`) | DM Sans | 20px | 600 |
| Section heading (`h2`) | DM Sans | 16px | 600 |
| Phase label | DM Sans | 10px | 700 (uppercase, letter-spacing 0.5px) |
| Role badge | DM Sans | 11px | 600 |
| Card title | DM Sans | 13px | 500 |
| Code / mono | `monospace` system stack | 13px | 400 |
| Muted meta | DM Sans | 11px | 400, `--text-muted` |

---

## 4. Spacing & Layout

**Base unit**: 4px. All spacing is multiples of 4.

**Page layout**:
```
app-header (fixed top, ~56px)
app-main (two columns, full remaining height)
  main-column (flex: 1, scrollable — board content)
  side-panel  (sticky top, ~320px wide — chat + notes + timeline)
```

On narrow viewports the side panel stacks below the main column (not yet responsive — planned).

**Typical padding**: cards `12px`, panels `16px`, wave headers `12–16px`.

---

## 5. Component States

### Status Chips

| Status | Color |
|--------|-------|
| `running` | `--gold-active` text on transparent |
| `done` | `--text-secondary` |
| `error` | `--type-security-fg` (dusty rose / red-adjacent) |
| `pending` | `--text-muted` |
| `failed` | `--type-security-fg` |

### Wave Cards
- Default: collapsed when `done` and no errors; expanded when `running` or has errors
- Left border: 2px solid role color (from role token)
- `wave-revision` class: distinct left border + `✎` badge, gold accent
- `wave-rework` class: `↻` badge, muted accent

### Task Cards
- Left border: 3px solid `var(--<role>)` token
- Hover: `--bg-card-hover`
- Error state: `--bg-tint-error` background + error text below title

### Buttons
| Class | Use |
|-------|-----|
| `.btn` | Default action — ghost style, border `--border-soft` |
| `.btn-primary` | Primary CTA — gold border, `--gold-active` text |
| `.btn` (disabled) | `opacity: 0.5`, `cursor: not-allowed` |

### Chat Bubbles
- User messages: right-aligned, `--bg-sprint-row` background
- Lead messages: left-aligned, `--bg-card` background

---

## 6. Iconography

No icon library. Uses inline Unicode / emoji characters for lightweight affordances:

| Symbol | Meaning |
|--------|---------|
| `▾` / `▸` | Expand / collapse |
| `✎` | User revision wave |
| `↻` | Rework wave |
| `👁` | Reviewer running |
| `☾` | Dark mode |
| `☀` | Light mode |
| `←` | Back |

---

## 7. Motion

No animation library. Transitions are CSS-only and minimal:

- Button hover: `background 0.15s ease`
- Card hover: `background 0.1s ease`
- No entrance animations, no loading skeletons (spinner text "Loading…" only)

Rationale: this is a tools-focused app. Motion would add visual noise without improving comprehension.

---

## 8. Accessibility Notes

- Theme toggle has `aria-label` and `title`
- Wave headers have `role="button"`, `tabIndex={0}`, `onKeyDown` for keyboard expand/collapse, and `aria-expanded` / `aria-label`
- Color contrast: light mode meets AA for body text and most badges; not formally audited
- Reduced-motion: no `prefers-reduced-motion` media query currently applied (no animations to suppress)
