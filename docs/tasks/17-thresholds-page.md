# 17 — Thresholds & Risk Settings Page

**Depends on:** 13
**Unlocks:** —

## Goal

The UI for task 11's write path — your own stop-loss/target lines and risk limits,
independent of any broker-side alerts (explicit spec requirement).

## Scope

`deck-app/src/pages/Thresholds.tsx`:
- **Thresholds table** — `GET /api/thresholds` already lists *every* holding with
  `stop_loss_pct`/`target_pct` (`null` if unset) — no need to cross-reference against
  `/api/dashboard` separately, this endpoint is already the complete, correct list.
  Editable inline inputs → `POST`/`PUT /api/thresholds`. **Enforce the sign convention
  in the input itself** (stop-loss accepts negative values only, target positive only)
  so the common mistake is caught before the request, not just via the backend's `422`.
- **Clear threshold** → `DELETE /api/thresholds?broker={broker}&symbol={symbol}`.
- **Risk Settings section**, same page (matches the UI prototype: both drive the
  Dashboard's Risk panel, so they live together) — `concentration_stock_pct`,
  `concentration_sector_pct` number inputs, and target India:US split as **one slider**
  (matches the prototype's existing single-slider UX — moving it derives both
  `target_india_pct` and `target_us_pct` server-side from a single value) →
  `PUT /api/settings/risk`.

## Out of scope

- No per-holding threshold *suggestions* — matches task 11's own scope, purely
  user-set values.

## Acceptance criteria

- Setting a threshold on one holding and reloading the page shows it persisted
  correctly, with every other holding's thresholds unchanged.
- **Editing only one field of an existing threshold (e.g. just `target_pct`) must not
  clear a previously-set `stop_loss_pct`.** The backend now handles a genuinely partial
  payload correctly (task 11's post-review fix), but the simplest correct frontend
  implementation is to always submit the complete current row (both fields, whatever
  their current values are) rather than relying on partial-payload semantics — verify
  whichever approach is used doesn't lose data, the same scenario the backend fix was
  written to prevent.
- Moving the India:US slider updates both displayed percentages immediately (client-side
  derivation, matching `target_us_pct = 100 - target_india_pct`, for instant feedback)
  and persists correctly in one `PUT` call.
- A stop-loss set here shows up as `threshold_breached: true` on the Dashboard (task 15)
  and as a stop-loss alert (task 14) once the holding's `pnl_pct` actually crosses it —
  full round-trip through the real backend, not just this page in isolation.
