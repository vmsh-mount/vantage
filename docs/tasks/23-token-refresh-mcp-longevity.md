# 23 — Token-Refresh Helper & MCP OAuth Longevity Measurement

**Depends on:** —
**Unlocks:** 24 (bridge-server as INDmoney MCP/OAuth client — needs a real answer on re-consent
frequency before it's built around an assumption)

## Goal

Two genuinely different problems bundled under one task number in the plan, because they're
both about reducing/understanding daily-auth friction:

1. **PaytmMoney's REST token dies at 6 AM daily by design** (verified live, task-18-era
   investigation) — reduce the friction of refreshing it from "several manual steps, easy to
   forget one" to as close to one-tap as this app's security posture allows (no OTP automation,
   ever — that's a hard line, not a task-23 decision).
2. **The INDmoney MCP's OAuth session longevity is unmeasured.** §3 of planning-phase2.md
   flags this explicitly: "auto-rotates and *may* need re-consent only occasionally —
   unmeasured." Task 24 (bridge-server becoming its own INDmoney MCP client) shouldn't be built
   around a guess.

## Scope

**Part 1 — one-tap PaytmMoney login helper**, extending `scripts/paytmmoney_login.py` in place
(not a rewrite): the existing flow already works (build login URL → user logs in → paste
redirect URL → exchange → write `.env`) but every session this phase has needed a *second*,
easy-to-forget manual step after that: restart `bridge-server` for the new token to take effect
(env vars are read once at process startup), then separately check the Status page to confirm
it actually worked. Concretely:
- `webbrowser.open(url)` the login URL automatically instead of requiring a manual copy-paste.
- After writing the new token, **restart the local `bridge-server` process** (find it by the
  same `uvicorn app.main:app` command line already used throughout this project, kill, relaunch
  with the same invocation, redirect logs the same way).
- **Verify**, not just assume: after restart, poll `GET /api/status` and print whether
  `paytmmoney.healthy` actually came back `true` — the script's own success message is only as
  good as a real check, not "the exchange call didn't throw."

**Part 2 — MCP OAuth longevity: start the measurement, don't fabricate an answer.** A single
session cannot observe "how often does this need re-consent" — that only emerges from
calendar-time passing while the connection is used normally. What task 23 *can* honestly do:
- Take today's data point: confirm the INDmoney MCP is currently reachable (a live tool call,
  e.g. `lookup_ind_keys` or `networth_snapshot`), and if INDmoney's own site exposes a
  "connected apps"/authorized-access page showing when this grant was first established (ask
  the user to check — same pattern as the PaytmMoney token-portal screenshot earlier in this
  project), record that as the actual start date rather than "as of right now."
- Create `docs/tasks/23-mcp-oauth-longevity-log.md` — a running log (date, connectivity check
  result, any re-consent event) that gets a new line whenever it's checked, across sessions,
  until a real pattern is visible.
- **Task 24 does not block on a fully-answered measurement** — it proceeds using whatever the
  log shows as of when it starts, explicitly stated as partial evidence, not a false certainty.

## Out of scope

- No OTP automation or credential storage for either broker, ever (hard invariant, not a
  task-23 tradeoff — see planning-phase2.md §2).
- No INDmoney equivalent of `paytmmoney_login.py` — INDmoney's live path in this project is the
  MCP (OAuth, browser-based consent), not a REST token requiring the same script-driven flow.
- No conclusion on MCP longevity from this task alone — that's the point of §Scope Part 2.

## Acceptance criteria

- Running the extended `paytmmoney_login.py` end to end (real login) results in: browser opens
  automatically, token is written, `bridge-server` is restarted automatically, and the script's
  own final output correctly reflects a real `GET /api/status` check — verified against an
  actual token refresh, not a dry run.
- `docs/tasks/23-mcp-oauth-longevity-log.md` exists with at least one real, dated entry from
  today confirming current INDmoney MCP connectivity (and the grant's actual start date, if
  discoverable from INDmoney's own settings).
- Nothing in task 24 or later is written as if MCP longevity were already known — it's treated
  as an open, tracked question until the log shows enough data to say otherwise.
