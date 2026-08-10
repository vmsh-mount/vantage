# 14 — Dashboard: Hero, Trend, Alerts, Risk (Tier 1)

**Depends on:** 13
**Unlocks:** 15 (extends the same `Dashboard.tsx` and its data-fetching)

## Goal

The above-the-fold half of the Dashboard page — everything planning.md's Query
Taxonomy calls Tier 1: "where do I stand," "am I exposed to something," "what needs my
attention today." This is the whole reason the app exists — get it right before the
secondary (Tier 2) content in task 15.

## Scope

`deck-app/src/pages/Dashboard.tsx` (Tier-1 section):
- **Net worth hero card** — `net_worth_inr`, `today_move_abs_inr`, `today_move_pct`
  from `GET /api/dashboard`.
- **30-day trend sparkline** — `GET /api/trend?days=30`'s `points` (`captured_at`,
  `total_net_worth_inr`), rendered with Recharts.
- **Alerts panel** — `GET /api/alerts`'s `alerts` list (`kind`, `broker`, `symbol`,
  `severity`, `title`). Style by `severity` (`"gain"` green / `"loss"` red), title
  string is already fully formatted server-side — render it directly, don't
  re-derive/reformat it client-side.
- **Risk panel** — `GET /api/risk`: `concentration_flags` (`kind`: `"stock"`|`"sector"`,
  `label`, `pct`, `limit_pct`) and `region_split` (`india_pct`, `us_pct`,
  `target_india_pct`, `target_us_pct`, `drift_pct`). **`drift_pct` and the
  `target_*_pct` fields are `null` until a target is set** (task 17) — render the
  actual split always, the drift line only when non-null. Don't show "null%" or a
  fabricated "0% drift."
- **"Refresh" button** in the page header (matches the UI prototype's wireframe) — calls
  `POST /api/refresh`, shows a loading state, then invalidates the dashboard/trend/
  alerts/risk queries so Tier-1 panels update without a full reload. **Handle the `429`
  response** ("a sync is already in progress") as a calm, expected state, not an error
  — it's the backend's actual concurrency-guard behavior (task 12), not a failure.

## Out of scope

- Breakdown charts and the holdings table — task 15.
- Full per-broker health detail and the dedicated refresh-and-wait flow — task 18's
  Status page owns that; this page's Refresh button is a convenience shortcut to the
  same endpoint, not a duplicate of Status's detail.

## Acceptance criteria

- All four Tier-1 pieces render correctly against the real running `bridge-server`
  with real portfolio data.
- Zero alerts renders a calm "nothing flagged" state, not a blank gap or broken-looking
  empty panel.
- No `RiskSettings` target set renders the real India:US split with the drift line
  omitted entirely — verified by checking `bridge-server`'s actual default state
  (`target_india_pct: null`) produces exactly this, not a placeholder value.
- Clicking Refresh shows a loading state, then updates the hero/trend/alerts/risk
  panels without a page reload; clicking it again immediately (while the first is
  still in flight) shows the 429 gracefully.
