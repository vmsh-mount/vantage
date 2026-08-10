# 09 — Trend API

**Depends on:** 05
**Unlocks:** —

## Goal

`GET /api/trend?days=N` — the secondary (Tier-2) net-worth-over-time chart, and the
data source for the Dashboard hero card's sparkline.

## Scope

`bridge-server/app/routers/trend.py`:
- Reads `PortfolioSnapshot`, returns the time series of `total_net_worth_inr` for the
  requested window (default 30 days, clamp to whatever history actually exists — no
  error on a fresh DB with less than N days, just return what's there).

## Out of scope

- No per-holding trend endpoint — that's what Trajectory (task 07) already covers,
  embedded per-row in the dashboard response.

## Acceptance criteria

- On a fresh DB with 3 days of snapshots, `?days=30` returns 3 points, not an error or
  padded/fabricated data.
- Points are in chronological order and match `PortfolioSnapshot.total_net_worth_inr`
  exactly for each `captured_at`.
