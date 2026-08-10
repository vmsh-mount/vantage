# 29 — Ask-Your-Portfolio Panel

**Depends on:** 28 (28a–28e, the runner + WS bridge + security scoping), 32 (holding notes)
**Unlocks:** — (the Half A payoff; §7's deferred apparatus builds on this if ever revived)

## Goal

The actual user-facing point of Phase 2 (planning-phase2.md §5.3): a persistent side panel in
deck-app where you can ask about your portfolio and get reasoned answers backed by task 25's
deterministic fact tools, task 26's MCP surface, and cited web search — "on-demand reasoning...
no journaling ritual, no memory tables, no grading apparatus."

## Scope

**Real check before designing anything**: does the panel need new backend work to "read the
holding notes from 32"? No — confirmed live via a real MCP `call_tool('get_dashboard', {})`:
`notes` is already a field on every holding in the response, because `DashboardHolding` (task 32)
and the `get_dashboard` MCP tool (task 26) share the same underlying function. Task 32's work
already flows through automatically.

**One genuinely new backend piece — the first real "UI action" tool**, proving the mechanism
planning-phase2.md §4 describes ("bridge an agent tool call onto the existing WebSocket to the
React SPA") rather than building out a large action vocabulary speculatively:
- **`highlight_holding(symbol: str)`** — a new Vantage MCP tool (`app/vantage_mcp.py`) that does
  no data work at all; its only purpose is to exist as a distinctly-named tool call the frontend
  recognizes and acts on locally (scroll-to + highlight a row on the Dashboard) as its
  `tool_use` event streams past on the WS, not as a generic "read this row's data" round-trip.
  One action is enough to prove the mechanism holds end-to-end; more can be added later without
  any protocol change.
- `agent_security.py`: `UI_ACTION_TOOLS`, `enable_ui_actions` flag on `build_scoped_extra_args`,
  same opt-in pattern as `allow_write`/`enable_web`.

**Panel defaults (a real decision, not an oversight)**: the panel calls
`build_scoped_extra_args(allow_write=True, enable_web=True, enable_ui_actions=True)`. `allow_write`
on by default here specifically — unlike task 26's own doc, which left it opt-in per call site —
because this *is* the call site task 26 wrote that decision for: "the agent can propose 'set
SWIGGY's stop to −7%' and actually do it," an explicit part of this panel's job, not a broker
order (invariant #1 is untouched — `set_threshold` never reaches PaytmMoney/INDmoney).

**`deck-app/src/hooks/useAgentSocket.ts`** (new) — owns the `/ws/agent` WebSocket connection:
send a prompt, receive the raw event stream, track connection/turn state. One connection per
mount, reused across turns (task 28c's session_id-based continuity happens server-side; this
hook just relays).

**`deck-app/src/components/AiPanel.tsx`** (new) — the four elements planning-phase2.md §6.1 names
by name:
- **Composer**: textarea + send, Enter-to-send (Shift+Enter for a newline).
- **Reasoning blocks**: `thinking` content blocks rendered as a muted, collapsed-by-default aside
  — visible if you want to check the model's own reasoning, not shouting for attention
  (§5's "clarity over volume").
- **Tool cards**: each `tool_use`/matching `tool_result` pair rendered as a compact card — tool
  name, arguments, a truncated result preview. This is where "every opinion sits on a number you
  can verify" (§1) becomes literal: the number's source is right there in the transcript.
- **UI-actions**: `tool_use` events named `mcp__vantage__highlight_holding` are intercepted before
  rendering as a generic card — instead they update a small `HighlightContext` (new,
  `deck-app/src/lib/highlight.tsx`) that `Dashboard.tsx`'s holdings table already reads to
  scroll-into-view + apply a highlight class to the matching row.

**`deck-app/src/components/Layout.tsx`** (modified) — the panel mounts once, alongside `Outlet`,
so it persists across page navigation (a React Router layout route's own children don't remount
on navigation) — a real "side panel," not a per-page widget. A toggle button opens/closes it.

**Two real bugs found and fixed during browser verification, not hypothetical:**
1. **`app/routers/agent_ws.py` (task 28c) was never updated to actually pass this task's new
   flags.** `build_scoped_extra_args()` was still being called bare (all defaults `False`) —
   confirmed live: `highlight_holding` came back permission-denied even though `enable_ui_actions`
   was supposedly the panel's default. The Scope decision above was correct; the WS endpoint just
   never got the memo. Fixed by passing `allow_write=True, enable_web=True,
   enable_ui_actions=True` explicitly at the one call site that constructs the panel's session.
2. **The UI-action handler fired on the `tool_use` block alone, before the real `tool_result`
   confirmed the call actually succeeded.** Caught by the bug above: the panel rendered
   "→ Highlighted GAIL on the Dashboard" and visually highlighted the row *while the underlying
   MCP call was simultaneously being denied* — the UI claimed something happened that hadn't.
   Fixed by correlating `highlight_holding`'s `tool_use` with its matching `tool_result` the same
   way regular tool cards already do, and only acting once `is_error` is confirmed false. A
   denied call now renders "⚠ Could not highlight X — denied by permission settings" instead of a
   false positive.
3. Also bumped the highlight's visible duration from an initial 3s to 8s after live testing
   showed 3s wasn't enough time to reliably notice or verify — a real UX finding from actually
   using it, not just a test-convenience tweak.

## Out of scope

- **No session persistence across a full page reload** — task 28c's own doc already flagged this
  as "task 29's concern," and the honest call here is: a reload starts a fresh conversation, no
  `session_id` persisted to `localStorage`. Revisit only if it turns out to matter in practice.
- ~~No markdown rendering~~ **Reversed as a follow-up, same day**: seeing it live, raw `##`/`**`
  in the response was genuinely bad UX, not just cosmetic — added `react-markdown` +
  `remark-gfm` (assistant responses regularly include real GFM tables, e.g. the concentration-
  risk breakdown). Scoped narrowly: only the final assistant text bubble renders as markdown;
  tool-card results and reasoning blocks stay plain `<pre>`/text, since those are raw JSON/
  reasoning, not prose meant to be formatted. `npm audit` flagged 4 pre-existing vulnerabilities
  in unrelated transitive deps (`nanoid`, `postcss`, `react-router`) — confirmed via
  `package-lock.json` diff that this install didn't touch those versions, so noted but not
  fixed here (out of scope for this change).
- **No more UI-action tools than `highlight_holding`** — see Scope above; the mechanism is what
  this task proves, not an exhaustive action vocabulary.
- **No voice/streaming-token UX polish** (`--include-partial-messages`) — task 28c already scoped
  this out; still true here.
- **No changes to task 25/26's existing tools** — the panel is a new consumer, not a rewrite.

## Acceptance criteria

All verified in a real browser session (deck-app dev server + live bridge-server), real `claude`
subprocesses, no mocks:

- A real question that requires a tool call (e.g. "what's my net worth and any concentration
  risk?") produces a visible tool card for the real `get_dashboard`/`get_risk` call, with the
  real returned numbers matching a direct API call for the same DB state. **Verified**: the
  panel's reported net worth, today's move, and concentration flags (e.g. SWIGGY/ICICIBANK over
  the configured limit) all matched `curl` against `/api/dashboard` and `/api/risk` exactly
  (real figures omitted here — personal portfolio data, not committed to this public repo).
  Expanding the tool card showed the identical raw JSON.
- A holding with a note set (task 32) is correctly referenced by the agent when asked something
  that note is relevant to — proving task 32's data genuinely reaches the model, not just that
  the field exists in a schema. **Verified**: asked "why do I own SWIGGY," the agent quoted the
  real note verbatim ("Bought after Q1 delivery-volume beat; holding through the margin-ramp
  story into FY27.") and reasoned about current P&L against that stated thesis.
- Asking the agent to highlight a specific holding triggers a real, visible scroll+highlight on
  the Dashboard's holdings table — verified in an actual browser session, not by inspecting the
  WS payload alone. **Verified after fixing the two bugs above**: confirmed via direct DOM
  inspection that GAIL's row received the `row-ai-highlight` class as a genuine causal result of
  the real tool call, not a stale/assumed state.
- The panel survives navigating between Dashboard/Manual Holdings/Thresholds/Status — connection
  and transcript both persist, not reset per page. **Verified**: navigated Dashboard → Thresholds
  via the real nav link; `ai-status-dot` stayed connected and the transcript was intact
  afterward. (A *full browser reload* does reset it, correctly, per the documented Out-of-scope
  decision — confirmed as the expected behavior, not confused with a bug.)
- `set_threshold` proposed and accepted through the panel actually writes to the `Threshold`
  table (confirmed via a direct DB read, same rigor as tasks 26/28b/28c's own verification) —
  and a request for something out of scope (e.g. asking it to place an order) is refused, citing
  invariant #1, not attempted. **Verified both**: "set a stop-loss of -12% on my GAIL holding"
  produced `stop_loss_pct: -12.0` on a direct `/api/thresholds` read (cleaned up after); "sell my
  entire SWIGGY position" was refused in-panel ("Vantage has no ability to place or execute
  orders... you'll need to place the order directly in the PaytmMoney app"), no tool call
  attempted.
- A real web-search-backed question (news/analyst commentary) produces an attributed answer,
  consistent with task 28e's already-verified `enable_web` behavior — not re-litigating that
  task's own adversarial testing, just confirming the panel's default flags actually enable it.
  **Verified**: "recent news on Suzlon Energy" returned real, dated news (Q1 results, a Tata
  Power EPC order, a new CEO) with four attributed sources (Trendlyne, Yahoo Finance, Business
  Standard) and connected it back to the user's actual SUZLON holding.
