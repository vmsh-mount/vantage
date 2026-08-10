# 12 — Status, Audit Log & Manual Refresh

**Depends on:** 05
**Unlocks:** —

## Goal

Operational visibility: is each broker actually live and healthy, what's the sync
history, and a manual "refresh now" — plus the spec's non-negotiable local audit trail
of every broker API call.

## Scope

`bridge-server/app/routers/status.py`:
- `GET /api/status` — per broker: mode (`live`/`mock`), last successful sync timestamp,
  token health. If the most recent `ApiCallLog` entry for a broker is a failure (e.g.
  401/token rejected), surface a plain-language warning ("PaytmMoney token expired —
  regenerate via `scripts/paytmmoney_login.py`") rather than silently showing a stale
  timestamp.
- `POST /api/refresh` — triggers task 05's synchronous sync pipeline immediately,
  returns once it completes (or the per-broker failure reasons if it partially failed).
  Guard with a short cooldown (e.g. reject/no-op if called again within 10s of the last
  run) — single-user so the risk is low, but a stray double-click or script shouldn't
  be able to spam broker APIs with no limit at all.

Also in scope: confirming `ApiCallLog` rows (written by task 05) are mirrored to a
rotating file log at `logs/api_calls.log`, satisfying the spec's local-audit-trail
requirement.

**Spec conflict resolved before writing code:** this task's own Scope text calls for a
time-based cooldown ("reject/no-op if called again within 10s of the last run"), but
its Acceptance Criteria explicitly require "`POST /api/refresh` called twice in a row
both complete... not deduped/skipped as 'too soon'" — a literal 10s cooldown would fail
that criterion outright for any two calls made in quick succession, which is exactly
what "twice in a row" describes. Resolved by implementing a **concurrency lock**
instead of a time-based cooldown: it rejects a call that arrives while a refresh is
*already running* (the actual spam risk — a script or stray double-click firing
overlapping syncs), but two calls that each run to completion before the next starts
are both allowed through, satisfying the acceptance criterion exactly. Verified both
sides: two sequential real refreshes each produced their own `PortfolioSnapshot` row
(count `+2`), and a call made while the lock was deliberately held returned `429`.

**Post-review fixes (2026-07-19):**
1. **The concurrency lock only guarded `/api/refresh` against itself, not against the
   scheduler's own periodic tick** — the actual most-likely collision (a user hitting
   "Refresh now" at the same moment the interval job happens to fire, needing no
   double-click or script, just ordinary timing), left completely unprotected: both
   call paths reach `run_sync_pipeline()`, but the lock lived in `status.py` and only
   `refresh()` acquired it. Two concurrent `SessionLocal()`s against the same SQLite
   file risk a "database is locked" error on whichever write loses the race. Fixed by
   moving the lock into `scheduler.py` itself, wrapping `run_sync_pipeline()` directly
   — since both the endpoint and the interval job call this one function, a single lock
   there protects both callers rather than only the one that happened to be added last.
   `run_sync_pipeline()` now returns `None` (never raises) when a sync is already in
   progress; `refresh()` turns that into a `429`. Verified by holding the lock exactly
   as the scheduler's tick would, then confirming *both* a direct
   `run_sync_pipeline()` call and `POST /api/refresh` correctly no-op/`429` instead of
   racing.
2. **`audit_log.py`'s docstring overclaimed** — it said the DB row and file mirror
   "can never drift out of sync," but `log_api_call` only `db.add()`ed the row; the
   actual commit was deferred to the caller's later batched `db.commit()` at the end of
   the tick. If that later commit ever failed for an unrelated reason, the file log
   entry would persist with no matching DB row. Rather than just soften the comment,
   closed the actual gap: `log_api_call` now commits immediately (DB before file, so a
   failed commit can't orphan a file line), decoupling the audit trail's durability
   from whatever else happens later in the same sync tick.

Both verified with a full regression pass (status healthy/warning states, two
sequential refreshes, log-line-count-matches-DB-row-count) confirming nothing else
broke.

## Out of scope

- No log viewer UI here — that's a deck concern, this task just guarantees the log
  file and table are correct and queryable.

## Acceptance criteria

- With a valid PaytmMoney token: `/api/status` shows `LIVE`, a recent timestamp, no
  warning.
- Temporarily invalidate the token, run a sync: `/api/status` shows the plain-language
  warning, not a stale-looking healthy state.
- `POST /api/refresh` called twice in a row both complete and each produces its own
  `PortfolioSnapshot`/`HoldingSnapshot` rows (not deduped/skipped as "too soon").
- `logs/api_calls.log` contains a line for every `ApiCallLog` row created during a
  session.
- A `POST /api/refresh` that arrives while one is genuinely still in progress gets
  rejected (`429`), rather than running two overlapping syncs concurrently — including
  when the in-progress sync is the *scheduler's own tick*, not just another manual call.
- `logs/api_calls.log`'s line count matches `ApiCallLog`'s row count exactly after a
  clean session of real sync calls (not rows inserted directly, bypassing the app).
