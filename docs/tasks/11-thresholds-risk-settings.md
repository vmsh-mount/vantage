# 11 — Thresholds & Risk Settings CRUD

**Depends on:** 02
**Unlocks:** full behavior of tasks 06 and 08 (they read this data; they don't need it
populated to run, but they're not meaningfully testable without it)

## Goal

The write path behind every threshold-breach and concentration flag elsewhere in the
app — your own stop-loss/target lines and risk limits, independent of any broker-side
alerts (explicit requirement from the original spec).

## Scope

`bridge-server/app/routers/thresholds.py`:
- `GET /api/thresholds` — all holdings with their current `stop_loss_pct`/`target_pct`
  (null if unset).
- `POST/PUT /api/thresholds` — set/update per broker+symbol.
- `DELETE /api/thresholds` — clear a holding's threshold.

`bridge-server/app/routers/settings.py`:
- `GET /api/settings/risk` — current `RiskSettings` row.
- `PUT /api/settings/risk` — update concentration %s and target India/US split (setting
  `target_india_pct` should also derive/require `target_us_pct = 100 - target_india_pct`,
  matching the single-slider UX already in the prototype).

**Post-review fix (2026-07-19):** `_upsert_threshold` unconditionally overwrote
`stop_loss_pct`, `target_pct`, and `notes` from the payload — but `ThresholdIn`'s
fields all default to `None` when omitted, so a follow-up call that only sets
`target_pct` (a realistic workflow: setting a profit target sometime after the
stop-loss was already in place) silently wiped the existing `stop_loss_pct` back to
`None`. The sibling endpoint in this exact same task, `update_risk_settings`, already
handled the analogous case correctly (`if payload.X is not None`) — this one just
didn't get the same treatment. Fixed to match. This is the third time this session a
"one sibling got the partial-update/aggregation treatment, the other didn't" bug has
surfaced (task 7's `thirty_day_days`, task 8's stock-concentration aggregation, task
10's `ltp` reset) — worth deliberately checking for this shape of asymmetry between
near-identical code paths going forward, not just each one in isolation. Verified the
exact scenario: set `stop_loss_pct`, follow up with a `target_pct`-only call, confirm
`stop_loss_pct` survives; same for a `notes`-only follow-up preserving both.

## Out of scope

- No per-holding threshold *suggestions* (e.g. auto-suggesting a stop-loss based on
  volatility) — purely user-set values, stored as-is.

## Acceptance criteria

- Set a stop-loss on a fixture holding, confirm `GET /api/dashboard` and
  `GET /api/alerts` both reflect it on their next call.
- Update `RiskSettings.concentration_stock_pct` from 15 to 10, confirm a previously
  unflagged holding at 12% now gets flagged by `GET /api/risk`.
- `PUT /api/settings/risk` with `target_india_pct=70` results in `target_us_pct=30`
  without a separate call.
- A `POST`/`PUT /api/thresholds` call that only includes one field (e.g. `target_pct`)
  never wipes a different field already set on that holding (e.g. `stop_loss_pct`) —
  partial updates only touch what's actually present in the payload.
