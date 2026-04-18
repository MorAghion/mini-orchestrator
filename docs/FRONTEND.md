# Mini Orchestrator — Frontend

**Version**: 1.0  
**Last updated**: 2026-04-16

---

## 1. Framework & Tooling

| Tool | Choice |
|------|--------|
| Framework | React 18 |
| Language | TypeScript |
| Bundler | Vite |
| Styling | Vanilla CSS (CSS custom properties) |
| Markdown | react-markdown |
| HTTP | native `fetch` |
| SSE | native `EventSource` |
| Tests | Vitest + React Testing Library + jsdom |

No global state library. All state is local React state + custom hooks. No router — single-page app with conditional rendering.

---

## 2. Project Structure

```
frontend/src/
  api/
    client.ts          typed REST wrapper + type definitions
  components/
    ArtifactViewer.tsx  modal for viewing generated docs
    Board.tsx           wave/task grid (main content area)
    Chat.tsx            lead chat panel
    PendingNotes.tsx    notes queue strip
    StageTabs.tsx       Documents / Code tabs
    Timeline.tsx        project event timeline
  hooks/
    useChat.ts         chat history + send
    useEventStream.ts  SSE connection + live events
    useNotes.ts        pending notes list + drop
    useProject.ts      project detail polling
    useTheme.ts        dark/light toggle (localStorage)
  labels.ts            display strings for roles, statuses, phases
  styles.css           all styles (metallic palette, components)
  App.tsx              root component + layout
  main.tsx             entry point
```

---

## 3. Component Tree

```
App
├── Header                    title, theme toggle, cost indicator, back button
├── ProjectList               (when no project selected)
│   └── project buttons
└── (when project selected)
    ├── StageTabs             Documents / Code tabs
    ├── main column
    │   ├── ShapingBoard      (status = shaping) brief preview
    │   └── Board             (status != shaping)
    │       ├── WaveRow*      one per wave
    │       │   └── TaskCard* one per task
    │       └── ReviewerRow   (status = stage1_review)
    ├── side panel
    │   ├── Chat              message history + composer + Launch/Apply CTAs
    │   ├── PendingNotes      queued note chips + drop button
    │   └── Timeline          event list + SSE indicator (hidden during shaping)
    └── ArtifactViewer        modal (when task clicked)
```

---

## 4. Pages / Views

Single-page app — no URL routing. View is determined by `projectId` state in `App`:

| State | View |
|-------|------|
| `projectId = null` | Project list |
| `projectId != null, status = shaping` | ShapingBoard + Chat |
| `projectId != null, status = planning / stage1_*` | Board + Chat + Notes + Timeline |
| `projectId != null, status = stage1_done` | Board + Chat (Refiner) + Timeline |

---

## 5. State Model

All state lives in `App.tsx` or in custom hooks. No global store.

| State | Location | Description |
|-------|----------|-------------|
| `projectId` | `App` | Selected project; `null` = project list |
| `openTask` | `App` | Task whose artifact is open in modal |
| `stage` | `App` | Active tab (`documents` \| `code`) |
| `launching` | `App` | Launch button loading state |
| `pendingRevision` | `App` | Revision suggestion string from Lead |
| `applyingRevision` | `App` | Apply button loading state |
| `data` | `useProject` | Full project detail (project + waves + tasks + events) |
| `messages` | `useChat` | Lead message history |
| `sending` | `useChat` | Message send in-flight |
| `events` | `useEventStream` | Live SSE events since page load |
| `connected` | `useEventStream` | SSE connection status |
| `notes` | `useNotes` | Pending notes list |
| `theme` | `useTheme` | `dark` \| `light`, persisted to localStorage |

### Key Derived State

**`allEvents`** — merged + deduplicated union of `data.events` (DB history) and live SSE `events`. Dedup key: `timestamp|type`. This ensures replay on reconnect and no duplicates.

**`status`** — `data?.project.status ?? "shaping"` — used for conditional rendering throughout.

**`readyToLaunch`** — `status === "shaping" && idea.trim().length > 0` — controls Launch button visibility.

---

## 6. API Client (`api/client.ts`)

Typed wrapper around `fetch`. Base URL: `/api` (proxied by Vite to `localhost:8000`).

Key methods:
```typescript
api.createProject()
api.listProjects()
api.getProject(id)
api.launchProject(id)
api.reviseProject(id, instruction, affectedRoles?)
api.getChatHistory(id)
api.sendMessage(id, content)
api.listArtifacts(id)
api.getArtifact(id, filename)
api.getReview(id)
api.getNotes(id)
api.dropNote(id, noteId)
```

**SSE** is opened directly via `EventSource` in `useEventStream`, not through the API client.

---

## 7. Hook Behaviour

**`useProject(projectId, tick)`**
- Fetches `GET /api/projects/{id}` on mount and whenever `tick` changes
- `tick` = `events.length` from `useEventStream` — SSE events trigger a refetch

**`useEventStream(projectId)`**
- Opens `EventSource` to `GET /api/projects/{id}/events`
- Auto-reconnects on disconnect (native `EventSource` behaviour)
- Accumulates events in state; resets when `projectId` changes

**`useChat(projectId)`**
- Loads history on mount; `send()` POSTs message and appends optimistically
- Returns `{ messages, sending, send, refresh }`

**`useNotes(projectId, tick)`**
- Fetches pending notes; `drop()` calls `DELETE /api/projects/{id}/notes/{noteId}`

---

## 8. Shared Patterns

### CTA Lifecycle Pattern
Revision suggestion (`pendingRevision`) is set by `handleSend` when the Lead reply contains `revision_request`. It is cleared:
- When the user clicks Apply (`handleApplyRevision`)
- When the user clicks Skip (`onDismissRevision`)
- Automatically when status transitions to `stage1_running` (useEffect)

This pattern is reusable for any ephemeral action suggestion surfaced from chat.

### Merged Event Feed
`allEvents` is computed with `useMemo` from `data.events` (historical) + `events` (live SSE), deduplicated by `${timestamp}|${type}`. Any component that needs a full event log should consume `allEvents`, not `data.events` or `events` separately.

### Phase Labels
`phaseLabelFor(status)` and `PROJECT_STATUS_LABEL[status]` in `labels.ts` are the single source of display strings for project phases. All components import from there; no inline status strings in JSX.

### Role Display
`ROLE_BADGE[role]` (emoji shorthand) and `ROLE_TITLE[role]` (full name) in `labels.ts`. TaskCard and WaveRow use these exclusively.

---

## 9. Testing Strategy

- **Unit**: `useChat`, `useNotes`, `useProject` hooks tested with mocked `api` client (`vi.mock("../api/client")`)
- **Component**: `Board`, `Chat`, `ArtifactViewer` with React Testing Library; mock API responses
- **No E2E** (yet) — smoke runner exercises the full stack manually

Test files live next to the component: `Board.test.tsx`, etc.
Setup: `src/test/setup.ts` loads `@testing-library/jest-dom` and cleans DOM after each test.
