# 19 — Cross-Page Integration & E2E Walkthrough

**Depends on:** 14, 15, 16, 17, 18
**Unlocks:** —

## Goal

The thing no single-page task can fully verify in isolation: that the four pages
actually behave as one coherent app — matches planning.md's original build step 8
("Frontend E2E walkthrough in browser: all four pages, charts, sorting, threshold
highlighting, manual CRUD, CSV import"), now that every page actually exists.

## Scope

- **Cross-page cache correctness**: adding a manual holding (task 16) must be visible
  on the Dashboard (14/15) without a manual refresh; setting a threshold (task 17)
  must show up as `threshold_breached` on the Dashboard and in Alerts without one
  either. Query invalidation was each page's own responsibility to wire up in tasks
  14–18 — this task is where a gap between two pages' invalidation would actually
  surface, since neither page alone can see it.
- **Global loading/error handling**: what every page shows when `bridge-server` isn't
  reachable at all (not just a slow response) — a clear "can't reach the backend"
  state, not a blank white screen or an infinite spinner.
- **Consistent formatting**: INR (`₹`) and USD (`$`) currency formatting, percentage
  formatting, and date/time formatting used the same way across all four pages —
  matches the UI prototype's existing `fmtINR`/`fmtUSD`-style helpers, ported once and
  shared, not reimplemented per page.
- **Full manual walkthrough** against the real running `bridge-server`, covering every
  item in planning.md's build step 8 checklist: all four pages load, breakdown charts
  toggle correctly, the holdings table sorts, threshold-breached rows highlight, manual
  holding CRUD works end to end, CSV import works end to end.

## Out of scope

- No new pages or endpoints — this task fixes integration gaps found between existing
  pages, not new features.

## Acceptance criteria

- Add a manual holding on the Manual Holdings page, switch to Dashboard without
  reloading: it's there.
- Set a stop-loss on the Thresholds page, switch to Dashboard: the row is amber and
  the Alerts panel shows it, without reloading.
- Stop `bridge-server` entirely and reload any page: a clear, non-broken "can't reach
  the backend" state, not a silent hang or a raw stack trace.
- Every checklist item from planning.md's build step 8 demonstrably works in one
  continuous walkthrough against the real backend.
