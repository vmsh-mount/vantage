# 15 — Dashboard: Breakdowns & Holdings Table (Tier 2)

**Depends on:** 14
**Unlocks:** —

## Goal

The below-the-fold half of the Dashboard: breakdown charts and the full holdings table
with the Trajectory column — Tier 2 per planning.md's Query Taxonomy, still valuable,
just not what you'd check two apps for.

## Scope

Extends `Dashboard.tsx`, using `GET /api/dashboard`'s already-fetched response (task
14's query, not a second fetch):
- **Portfolio-wide gain/loss** — `total_pnl_abs_inr`/`total_pnl_pct`, a real API field
  with no assigned home until now (planning.md's Query Taxonomy lists "portfolio-wide
  gain/loss" as Tier 2 explicitly, alongside per-position — this is that field). A
  one-line summary figure near the breakdown toggle or above the holdings table, not a
  new component — this exists specifically because task 6's review caught it missing
  from the API in the first place; it shouldn't now ship with no UI ever reading it.
- **Breakdown toggle** — `[By Broker] [By Asset Class] [By Sector] [India/US]` buttons
  switching between `breakdowns.by_broker` / `by_asset_class` / `by_sector` /
  `by_region`, each a list of `{label, value_inr, pct}`. Render as a donut or bar chart
  (Recharts).
- **Holdings table** — one row per `DashboardHolding`: `symbol`, `broker`, `quantity`,
  `ltp`, `market_value_inr`, `pnl_pct`, sortable columns. Row gets the established
  breach tint (`row-breach`, red/`--loss-soft` — same convention as architecture.md's
  wireframe and the UI prototype's CSS) when `threshold_breached` is `true`. Amber
  (`row-near`/`--warn-soft`) is the *near*-but-not-breached state from that same
  convention — out of scope here, since `DashboardHolding` only exposes
  `threshold_breached` as a boolean, no distance-to-threshold figure to derive "near"
  from.
- **Trajectory column** — renders `DashboardHolding.trajectory` (`TrajectoryOut`):
  - `static: true` → "Static — priced by you" (manual holdings, never a chart).
  - `cold_start: true` → "Gathering history (day `{days_available}` of 30)".
  - Otherwise → text stats, `{recent_days}d: {recent_return_pct}%` next to
    `{thirty_day_days}d: {thirty_day_return_pct}%` (no sparkline — `TrajectoryOut`
    (task 7) only ever carries these scalar fields, never a points/series array, so
    there is nothing to chart; a per-holding price series would need its own backend
    follow-up, not a silent client-side fabrication), and — only when `flag_kind` is
    non-null — a chip with `flag_text` (colored by `flag_kind`: `"unusual"`/`"streak"`
    up vs down / `"near_high"`/`"near_low"`).
  - **Both day-counts must come from the API's `recent_days`/`thirty_day_days` fields,
    never hardcoded to "7d"/"30d".** The backend went through two rounds of review
    fixes specifically to make these dynamic (docs/tasks/07-trajectory.md) — a
    hardcoded label here would silently reintroduce the exact bug that was fixed twice.

## Out of scope

- No new data fetching — this task renders fields already present in task 14's
  `GET /api/dashboard` response.

## Acceptance criteria

- `total_pnl_abs_inr`/`total_pnl_pct` render somewhere on the page — the field exists
  and is correct on the backend (verified in task 6); this task's job is just to not
  leave it unused.
- Each breakdown dimension's rendered values sum to 100% (or to `net_worth_inr` in INR
  terms) — no holding silently dropped from the chart.
- Trajectory column correctly renders all four states — reuse the same fixture
  scenarios already validated in `bridge-server`'s task 7 tests (an unusual mover, a
  multi-day streak, a near-30-day-high, a cold-start holding, a manual/static holding)
  as the manual QA scenarios here, rather than inventing new ones.
- A holding with 5 days of history shows "5d" (not "7d") on the recent-window figure;
  one with 8 shows a genuine "7d" — verified against seeded `HoldingSnapshot` data at
  exactly these boundaries, matching the backend's own boundary tests.
- Threshold-breached rows are visibly tinted (red, `row-breach`); non-breached rows are not.
