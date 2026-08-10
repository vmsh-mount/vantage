# 06 — Dashboard API

**Depends on:** 05
**Unlocks:** 07 (Trajectory is embedded in this endpoint's response)

## Goal

`GET /api/dashboard` — the single endpoint the whole Dashboard page is built from. This
is Tier-1 query category #1 from planning.md's Query Taxonomy ("where do I stand right
now").

## Scope

`bridge-server/app/routers/dashboard.py`:
- Net worth: sum of `market_value_inr` across all current `Holding` rows.
- Today's move, per holding: `qty * (ltp - close_price)` **if `close_price` is set**;
  otherwise fall back to `latest HoldingSnapshot value - first HoldingSnapshot value of
  today` (null/zero before a second tick has happened that day — don't fabricate a
  number). For `source='manual'` holdings, today's-move is not computed at all — see
  the "static" treatment below. Portfolio-wide today's move sums whatever each holding
  contributed, converted to INR, both absolute and as a % of yesterday's net worth.
- Breakdowns: by broker, by asset class, by sector, by India/US — each as a list of
  `{label, value_inr, pct}`. **India/US is derived from `exchange`** (NSE/BSE→India,
  NASDAQ/NYSE→US), not from `asset_class` — see architecture.md's Data Model note on
  why (an ETF's `asset_class` doesn't tell you its region).
- Manual holdings (`source='manual'`) get a `pricing: "static"` marker in the response
  instead of a today's-move figure — the deck uses this to render "Static — priced
  by you" instead of a move percentage (Key Decision #9, planning.md).
- Per-position and portfolio-wide gain/loss (`pnl_abs`, `pnl_pct`, vs `avg_cost`).
- Threshold-breach flag per holding (reads `Threshold` from task 11 — if that table is
  empty, no holding is ever flagged; this task doesn't require 11 to be done first,
  just tolerates it being empty).

## Out of scope

- Alerts, Risk, Trend, Trajectory are their own tasks (07–09) — this task defines the
  base response shape they attach to, but doesn't compute them.
- No manual-holdings write path — this endpoint is read-only.

**Post-review fix (2026-07-19):** the initial implementation was missing the
portfolio-wide gain/loss total this task's own scope calls for — only per-position
`pnl_abs`/`pnl_pct` made it into the response. Added `total_pnl_abs_inr`/`total_pnl_pct`
to `DashboardOut`, computed the same way as `today_move_abs_inr`/`today_move_pct`
already were: `pnl_abs` is native-currency, normalized to INR via the
`market_value_inr / market_value` ratio per holding before summing (a naive
`sum(h.pnl_abs)` would silently add INR and USD once task 10's manual holdings exist).
Also added a `close_price == 0` guard (falls back to the snapshot-delta path instead of
a `ZeroDivisionError` → 500) — low-severity, essentially unreachable for a real stock
price, but a one-line fix. Verified against the same fixture set plus a real-data check
where all holdings are currently INR-only, confirming the normalized total exactly
matches a naive sum in that case (no regression) while being correct for the mixed-
currency case the naive version would have gotten wrong.

## Acceptance criteria

- Matches the `GET /api/dashboard` row in architecture.md's API Surface table.
- Response's net worth total equals the sum of all `market_value_inr` in `Holding` at
  call time — verified against a hand-computed total from a known fixture set.
- Every breakdown's values sum back to the total net worth (no holding silently
  dropped from any breakdown).
- A holding with no `Threshold` row set is never flagged as breached.
- A fixture ETF holding trading on NASDAQ buckets under US in the India/US breakdown
  even with `asset_class='etf'` (not `'us_equity'`) — the exchange-based rule, not the
  asset-class-based one.
- A manual holding never contributes to today's portfolio-wide move and carries
  `pricing: "static"` in its response object.
- `total_pnl_abs_inr` equals the sum of each holding's `pnl_abs` normalized to INR
  (not a naive sum across currencies) — verified with a fixture set mixing INR and
  USD holdings, matched to a hand-computed expectation to floating-point precision.

