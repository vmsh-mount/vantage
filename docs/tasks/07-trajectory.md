# 07 — Trajectory

**Depends on:** 05, 06
**Unlocks:** —

## Goal

Per-holding trajectory embedded in the dashboard response — Tier-1 query category #4:
"is today's move unusual for *this* stock, or just noise?" The exact algorithm is
already specified in architecture.md's Trajectory section; this task is just
implementing it.

## Scope

Extend `routers/dashboard.py`'s per-holding response objects with a `trajectory` field,
computed from `HoldingSnapshot` — **for `source='api'` holdings only** (see the
manual-holdings item below):
1. Dedupe same-day snapshots to one closing value per calendar day, trailing 30 days.
2. Recent-window and 30-day cumulative % return, always both, always shown together.
   The recent window is `min(7, days_available - 1)` days — **label it by that actual
   number**, not a hardcoded "7d". At 5 days of history this is a "5d" return, not a
   mislabeled "7d" one; it only becomes "7d" once ≥8 days have accumulated. This is
   the fix for the earlier spec bug where `MIN_DAYS_FOR_STATS = 5` could produce a
   "7d" figure with no day-7 data point behind it.
3. Unusual-move flag: `z = today's % move / stdev(trailing daily % returns)`,
   `|z| ≥ 1.5` → flag with the multiplier ("2.3× its typical daily swing"). **This
   same flag is what `GET /api/alerts` (task 8) reuses for its big-mover check** — do
   not duplicate the z-score computation there; expose it as a shared function both
   routers call.
4. If no unusual-move flag: streak ≥3 same-direction days, or within 0.5% of the
   30-day high/low, as fallback flags.
5. Cold start (live-synced holdings only): fewer than 5 days of `HoldingSnapshot`
   history for a symbol → no stats/flag, just `{cold_start: true, days_available: N}`.
6. **Manual holdings (`source='manual'`) always return `{static: true}`**, never
   `cold_start` — there's no live feed for them to accumulate history from (Key
   Decision #9, planning.md), so "gathering history" would wrongly imply it resolves
   over time. Deck renders this as "Static — priced by you".

**Post-review fix (2026-07-19):** the initial implementation applied the "label it by
actual days available" fix (item 2 above) to the recent-window return only —
`thirty_day_return_pct` kept anchoring at `historical[0]` with no day-count of its own,
silently mislabeling it as "30-day" for every holding's first ~25 days of life (exactly
the same bug the recent-window fix already exists to prevent, just not applied to the
other number sharing the same root cause). Concretely: at the `n=5` boundary,
`recent_anchor` and `oldest` are the same index, so `recent_return_pct` and
`thirty_day_return_pct` come out numerically identical — one correctly labeled "5d",
the other silently implying "30d". This task's own review-fixture (≥30 days seeded)
never exercised the window where it mattered, so it shipped undetected; caught by
inspecting `n=5` output where both figures printed as identical numbers with different
implied labels. Fixed with a `thirty_day_days` field mirroring `recent_days`, same
pattern, applied symmetrically this time. Verified at `n=5` (both fields read "5d",
now correctly labeled instead of one lying), `n=8` (`thirty_day_days=8`, distinct
from `recent_days=7`), and `n=30` (`thirty_day_days=30`, genuine full window).

## Out of scope

- No historical backfill from an external market-data source (explicit decision in
  planning.md) — this task only ever reads what's already in `HoldingSnapshot`.
- No separate per-holding endpoint — this is batched into `/api/dashboard`, not called
  once per row (see architecture.md's rationale).

## Acceptance criteria

- Freshly-synced DB (day 1, one snapshot only): every holding's trajectory shows
  `cold_start: true, days_available: 1`.
- Seed ≥30 days of fixture `HoldingSnapshot` rows matching the scenarios already
  validated in the UI prototype (a big one-day mover, a multi-day streak, a new
  30-day-high) and confirm the computed flags match what the prototype shows for the
  same fixture shapes.
- A holding with exactly 5 days of history gets real stats, not cold-start (boundary
  check on the `MIN_DAYS_FOR_STATS = 5` threshold) — and its recent-window figure is
  labeled "5d", not "7d".
- A holding with exactly 8 days of history shows a genuine "7d" label.
- A fixture manual holding returns `{static: true}` regardless of how many
  `HoldingSnapshot` rows exist for it (even zero) — never `cold_start`.
- `thirty_day_days` accurately reflects the actual historical window used, not a
  hardcoded 30 — verified distinct from `recent_days` once history exceeds 7 days
  (`n=8` → `recent_days=7`, `thirty_day_days=8`, two different numbers), and correctly
  equal to it (both genuinely "5d") at the `n=5` boundary where they coincide.
