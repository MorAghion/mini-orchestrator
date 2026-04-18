# Manual Test Plan

**Purpose**: One-time acceptance run before Stage 2 work begins.  
**Update this file**: check boxes as you go, note any failures inline.

---

## Project Idea

Use this idea for all three scenarios:

> **"A personal bookmark manager — save URLs with tags and a short note, browse and search saved links, mark favourites, and one-click open. Single-user, browser-based, no login."**

Simple enough to run fast; complex enough to touch all 8 doc agents (has screens, auth-free security posture, frontend state, backend API, DevOps).

---

## Scenario 1 — Full Stage 1 run

### Steps
1. Open app → click **+ Start new project**
2. In the chat, describe the idea above (copy-paste it verbatim or rephrase naturally)
3. Continue chatting with the Lead until it proposes a brief and the **Launch Stage 1** button appears
4. Click **Launch Stage 1**
5. Watch the board — waves should appear and agents should complete one by one
6. After all waves complete, the Reviewer runs automatically
7. Wait for `stage1_done`
8. Click any completed task card to open its artifact

### Expected
- [x] Shaping phase: Lead asks at least one clarifying question, then proposes a brief
- [x] Brief accepted: **Launch Stage 1** button appears below chat
- [x] After launch: project transitions `shaping → planning → stage1_running`; board shows wave rows
- [x] Wave 1 (PRD) completes first; subsequent waves appear in dependency order
- [x] No more than 3 task cards show `running` at the same time
- [x] All 8 task cards reach `done`
- [x] Reviewer row appears briefly (`stage1_review`), then disappears
- [x] Project reaches `stage1_done`; board header shows "8/8 agents done"
- [x] Clicking a task card opens a modal with rendered markdown — not blank, not raw HTML
- [x] Cost indicator in header shows a non-zero API-equivalent amount
- [x] Timeline panel shows a chronological event list (wave started/completed, task events, review)
- [ ] **[BUG]** Timeline reviewer row — clicking the `▸` chevron expands inline issue list. Currently the row lights up on hover even when the button is disabled (CSS hover applies to the whole row regardless of interactivity). Fix shipped; verify the expand actually works and shows the 6 issues with severity + suggested fix.

### Note — what "approved with N issues" means
The Reviewer uses two verdicts:
- **`needs_rework`** — at least one high-severity issue. Triggers an automatic rework wave: flagged agents re-run with the reviewer's feedback injected, then Stage 1 finishes.
- **`approved`** — only low/medium severity nits; nothing blocks Stage 2. No rework wave fires. Issues are logged (expandable in the Timeline) but do NOT auto-trigger any action.

So 6 issues with "approved" = cosmetic/low-severity suggestions. The Refiner persona is now active — you can ask it to act on any of them if you want, or ignore them and proceed to Stage 2.

---

## Scenario 2 — User revisions (2 requests)

_Continue from the same project after Scenario 1 completes._

### Revision A — Scope change
1. In chat (now in Refiner mode), send:  
   **"Actually add a simple tagging system where tags are coloured — each tag gets a user-assigned colour."**
2. Lead should suggest a revision. Click **Apply**.
3. Watch the board for a new "User revision wave" row.
4. After it completes, check the PRD and FRONTEND artifacts.

### Expected (Revision A)
- [x] Lead replies in Refiner persona (no "Launch" button, no narration style)
- [x] A revision suggestion CTA appears ("Apply" + "Skip" buttons)
- [x] Clicking Apply: project transitions to `stage1_running`; Apply CTA disappears
- [x] A new "User revision wave" row appears on the board with `✎ User revision` badge
- [x] Wave shows only the affected roles (not all 8)
- [ ] After wave completes + Reviewer re-runs, project returns to `stage1_done`
- [ ] PRD artifact now mentions coloured tags
- [ ] Skip button works: send another message → suggestion appears → click Skip → CTA disappears without triggering a revision

### Revision B — Targeted single doc
1. Send:  
   **"The security doc should explicitly note that all saved URLs are stored only in the user's browser localStorage — no server-side persistence of URLs."**
2. Apply the suggestion.
3. After completion, open the SECURITY artifact.

### Expected (Revision B)
- [ ] Second revision wave appears below Revision A on the board (both visible, grouped under "User revisions (N)" divider)
- [ ] Revision B wave runs only the relevant doc(s) — not a full re-run
- [ ] SECURITY artifact now mentions localStorage-only storage

---

## Scenario 3 — Notes dropped during a run

_Start a fresh project (use the same idea or any short idea)._

### Steps
1. Create a new project, shape a brief, launch Stage 1
2. **While the wave is running** (at least one task in `running` state), type in the chat:  
   **"Make sure the PRD includes an offline mode — the app should work without internet after initial load."**
3. Watch the pending notes strip below the chat.
4. Let Stage 1 run to completion.

### Expected
- [x] Chat response uses Narrator persona ("noted, I'll pass that to the Reviewer" style), not Shaper or Refiner
- [x] A note chip appears in the **PendingNotes** strip below the chat
- [ ] The chip disappears automatically when the Reviewer runs (absorbed)
- [ ] The final Reviewer verdict references the offline mode requirement (check `review_report.json` via the Timeline review section or the artifact viewer)
- [ ] If the Reviewer flagged a gap, a rework wave appears on the board (labeled "Rework wave" with `↻ Fix pass` badge)
- [ ] Drop test: add a second note while running, then click **×** on its chip before the Reviewer runs — chip disappears and is NOT passed to the Reviewer

---

## Known bugs / deferred fixes

- **[BUG]** `×` button on pending note chips does not work — clicking it has no effect; the chip stays. Needs investigation (likely a click handler or API call issue in `PendingNotes`).
- **[UX]** Reviewer summary in chat is too verbose — full issue list with category, description, fix, and affected files makes the message very long. Fix: show a one-line summary (verdict + count) with a collapsible "Show details" section, so it doesn't hammer the chat view.

---

## Regression checks (run at the end)

After all three scenarios:

- [ ] **Project list**: all three projects appear on the home screen with correct status labels
- [ ] **Delete**: click `×` on one project → confirm dialog → project removed from list
- [ ] **Dark / light toggle**: switch theme — board, chat, timeline all re-style correctly; preference survives page reload
- [ ] **Back button**: navigate into a project → click ← Back → lands on project list (not blank)
- [ ] **SSE indicator**: green dot shown in Timeline while on the project page; navigate away and back — indicator reconnects
- [ ] **Cost indicator**: non-zero for completed projects; shows "$0 paid" + API equiv; tooltip text is readable
