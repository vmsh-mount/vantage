# 18 — Status Page & Manual Refresh

**Depends on:** 13
**Unlocks:** —

## Goal

Operational visibility: is each broker actually live and healthy, and a manual
"refresh now" with the full detail — the dedicated home for what task 14's Dashboard
Refresh button only shortcuts to.

## Scope

`deck-app/src/pages/Status.tsx`:
- **Per-broker card** — from `GET /api/status`'s `brokers` list: `mode` badge
  (`"live"`/`"mock"`), `last_sync_at` (render as relative time, e.g. "2 minutes ago"),
  `healthy` indicator, and `warning` text when unhealthy (the backend already produces
  a complete plain-language message, e.g. "paytmmoney token expired or rejected —
  regenerate via `make login`" — render it directly, don't re-derive or truncate it).
- **"Refresh now" button** → `POST /api/refresh`, loading state while in flight, then
  refetch both status and dashboard queries. **Handle `429`** ("a sync is already in
  progress") as an expected, calm state — this is the backend's real concurrency guard
  (task 12: it protects against the scheduler's own periodic tick colliding with a
  manual refresh, not just double-clicks), not an error condition. Show something like
  "already refreshing — hang on" rather than a failure toast.

## Out of scope

- No log viewer for `logs/api_calls.log` — matches task 12's own scope, that file is
  for tailing directly, not a UI concern.

## Acceptance criteria

- A healthy broker (valid token, or mock mode) renders with no warning.
- An unhealthy broker (verified by temporarily invalidating the real PaytmMoney token,
  or seeding a failed `ApiCallLog` row the same way the backend's own task 12 tests
  did) renders the plain-language warning clearly, not a stale-looking healthy state.
- Clicking Refresh shows a loading state, then updates both this page and the
  Dashboard's data.
- Clicking Refresh twice in rapid succession — or while the scheduler's own background
  tick happens to be running — shows the `429` gracefully instead of an error.
