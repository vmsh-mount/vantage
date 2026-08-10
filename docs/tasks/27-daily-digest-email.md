# 27 — Daily Deterministic Email Digest

**Depends on:** 22 (tax suggestions), 25 (fact tools — sequencing only, see Scope below)
**Unlocks:** — (first agent-free Half A deliverable; §7's agent-authored desk note replaces this
later, once the panel demonstrates what's actually worth ranking)

## Goal

A daily email, **composed and sent entirely in Python** (planning-phase2.md §5.4) — no agent, no
MCP call, so it genuinely always sends regardless of INDmoney/Claude Code availability. Content:
holdings summary, tax/LTCG dates approaching, threshold breaches, concentration flags — exactly
the four things §5.4 names, ranked clarity-over-volume (§5's presentation principle), with a
**dead-man's switch** that reports its own failure loudly rather than silently not sending.

## Scope

**Real scope decision, not just following the table literally:** the task table lists "22, 25" as
depends-on, but §5.4's own content list — "holdings, tax/LTCG dates approaching, threshold
breaches, concentration flags" — never mentions volatility-stops or benchmark (task 25's actual
new outputs). Re-reading why: §5.4 says this digest exists specifically **"without the
agent-dependency that made v1's version fragile... No agent, no MCP mesh, no auth fragility — so
it genuinely always sends."** Task 25's vol-stops/benchmark tools depend on bridge-server's own
INDmoney MCP client (task 24) — real OAuth token state, a real 30-calls/min rate limit that can
force a ~2-minute wait (confirmed live in task 25), the exact "MCP mesh" and "auth fragility"
this task's design principle exists to avoid. Building the digest on top of that would make
"genuinely always sends" false on any morning the MCP token needs re-consent or the rate limit is
already warm from other use. **So this task's content pulls only from the DB and Phase-1/task-22
logic that's already synchronous and local** — the "25" dependency is sequencing (build order),
not a content requirement. If vol-stops/benchmark belong in a future digest, that's a deliberate
call to make later with the fragility explicitly accepted, not a default.

**Content, reusing existing verified functions directly (no logic duplicated):**
- **Needs attention now** (pinned top, per §5's presentation principle): stop-loss breaches from
  `get_alerts` (`kind == "stop_loss"`) + LTCG-crossing-soon suggestions from `get_tax_suggestions`
  (`kind == "ltcg_crossing_soon"`) — the two genuinely time-sensitive categories §5 names by name.
- **Tax opportunities**: harvest_loss/harvest_gain suggestions from `get_tax_suggestions`, ranked
  by `amount_inr` descending — real rupees, most valuable first.
- **Concentration flags**: from `get_risk`.
- **Big movers today**: from `get_alerts` (`kind == "mover"`) — least time-sensitive, ranked last.
- **Summary footer**: net worth, today's move, total P&L — from `get_dashboard`'s summary fields
  only, not the full holdings table (clarity over volume — the dashboard itself is one click away
  for anyone who wants every row).
- Every section that's empty is simply omitted, not rendered as "nothing to report" — an email
  that's mostly empty sections isn't clearer than a shorter one.

**Dead-man's switch, scoped honestly for a local single-user app with no second always-on
process (invariant #4 rules out a real external watchdog):**
1. The whole run is wrapped so a failure can never just vanish. On any exception during
   composition or sending, the job attempts a **separate, minimal fallback email** — hardcoded
   plain text, no dependency on whatever broke in the main composer — so a bug in, say, the tax
   suggestions query doesn't also silence the failure notice.
2. Every run (success or failure) writes a `DigestLog` row and a line to
   `logs/digest_failures.log` on failure — durable, inspectable state, same pattern as
   `ApiCallLog`/`audit_log.py`.
3. **The actual dead-man's-switch behavior**: each run checks whether *yesterday's* scheduled run
   ever recorded success. If not, today's email (or today's fallback, if today also fails) leads
   with an explicit "⚠ digest didn't send on \<date\>" banner — so a silent failure surfaces the
   very next time anything successfully reaches the inbox, instead of being forgotten. This is
   the honest ceiling without inventing a second daemon process that doesn't fit this project's
   local/single-user shape.
4. Last-run status/timestamp is exposed on `GET /api/status` too (extends `StatusOut`), so it's
   visible in the app even if you never check email.

**New:** `bridge-server/app/digest.py` (compose + render + send + dead-man's-switch logic),
`bridge-server/app/models/digest_log.py` (`DigestLog`), `bridge-server/app/schemas/digest.py` if
a response model is needed for the status extension.
**Modified:** `app/config.py` (SMTP + recipient + send-time settings), `.env.example`,
`app/scheduler.py` (new daily cron job, explicit `Asia/Kolkata` timezone rather than trusting the
host OS's local tz), `app/routers/status.py` (surface last digest run).

Uses stdlib `smtplib`/`email` — no new dependency.

## Out of scope

- No agent-authored ranking or narrative — that's §7's deferred desk note, once the panel (task
  29) shows what's actually worth ranking beyond this deterministic ordering.
- No vol-stops/benchmark content (see Scope decision above).
- No real external dead-man's-switch service (e.g. a third-party heartbeat ping) — out of
  keeping with invariant #4 (local, single-user, no cloud dependency for core function).
- No HTML template engine/framework — plain Python string composition, matching this project's
  existing "no unnecessary dependency" pattern.
- No digest history UI page — `DigestLog` exists for the dead-man's-switch check and `/api/status`
  surfacing, not as a new browsable feature; add one later only if it's actually wanted.

## Acceptance criteria

- A real email sends via real SMTP credentials to a real inbox — inspected for actual content
  correctness, not just "the send call didn't raise." **Verified**: real SMTP credentials added
  to `.env`, `run_daily_digest()` run for real, user confirmed the email arrived and its content
  (net worth, concentration flags, big movers) matched what a direct DB check showed.
- Content matches live DB state: a stop-loss breach, a tax suggestion, and a concentration flag
  seeded/confirmed for real all appear correctly in the rendered output. **Verified for
  concentration** (real holdings over the configured limit, matched `/api/risk` exactly —
  figures omitted here, personal portfolio data) **and movers** (11 real unusual-move flags,
  matched Trajectory's own numbers). **Not independently verified for stop-loss/tax-opportunity
  sections** — no threshold is currently
  breached and no Tax P&L/Harvesting Report is imported in this session's DB (only the Trade Book
  was re-imported, for task 25's benchmark verification), so those sections legitimately rendered
  empty rather than being exercised. The code path is identical to the already-verified
  concentration/movers sections (same `get_alerts`/`get_tax_suggestions` calls task 22 already
  verified independently) — a real gap in *this task's* live verification, not glossed over.
- Simulated failure (e.g. a broken SMTP config) still produces *some* loud signal — the fallback
  email attempt is exercised, or failing that, `logs/digest_failures.log` and the `DigestLog` row
  are confirmed to exist with the right status. **Verified both branches**: (1) with `SMTP_HOST`
  blank, both the main send and the fallback send failed as expected, and both were captured in
  `digest_failures.log` + a `DigestLog(status="failed")` row; (2) with real SMTP configured,
  `build_digest` was made to raise via a mocked failure, and the *fallback* email genuinely sent —
  user confirmed receiving a real "Vantage digest FAILED" email — with `DigestLog(status=
  "fallback_sent")` recorded.
- The "yesterday didn't send" banner is confirmed to appear when the prior day's `DigestLog` has
  no success row — not just asserted from reading the code. **Verified via direct function call**
  against real DB state (`_missed_or_failed_previous_run` + `render_text` after a real recorded
  failure) — the banner text rendered correctly ("[!] digest failed on 29 Jul 2026 (...)").
  **Design note found while verifying**: the banner only fires when the last run's status is
  exactly `"failed"`, deliberately *not* `"fallback_sent"` — a fallback send already reached the
  inbox with a loud failure notice, so re-flagging it on the next regular digest would be
  redundant; only a fully silent failure (neither email reached anyone) needs the extra prompt.
  Not re-verified via an actual second live send, to avoid needlessly spamming a real inbox for a
  code path already exercised at the function level against real data.
- Scheduled job registered with an explicit `Asia/Kolkata` trigger, confirmed via APScheduler's
  own job listing (not just "the code looks right"). **Verified**: `sched.get_jobs()` showed
  `daily_digest -> cron[hour='7', minute='0']`, next run `2026-07-30 07:00:00+05:30`.
