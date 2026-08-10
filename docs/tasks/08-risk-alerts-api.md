# 08 — Risk & Alerts API

**Depends on:** 05, 06, 07 — reuses 06's net-worth/market-value helper rather than
re-summing `Holding` independently, and reuses 07's unusual-move z-score for the
big-mover check rather than a separate flat-% rule (see Scope).
**Unlocks:** —

## Goal

`GET /api/risk` and `GET /api/alerts` — Tier-1 query categories #2 and #3: "am I
exposed to something I shouldn't be" and "what actually needs my attention today."

## Scope

`bridge-server/app/routers/risk.py`:
- `GET /api/risk` — reads `RiskSettings` (task 2/11), computes:
  - Single-stock concentration flags: **aggregated by symbol** (not per-`Holding`-row)
    whose combined `market_value_inr` / net worth ≥ `concentration_stock_pct`. The same
    stock split across two brokers (e.g. RELIANCE via both PaytmMoney and INDmoney) is
    one real exposure, not two smaller ones that individually hide under the limit —
    aggregate first, exactly like the sector check below already does, before
    comparing against the threshold.
  - Sector concentration flags: same check aggregated by sector ≥
    `concentration_sector_pct`.
  - India:US split vs `target_india_pct`/`target_us_pct` (both null → report actual
    split with no drift/target comparison).

`bridge-server/app/routers/alerts.py` (or folded into `risk.py` — implementer's call, both are
thin read endpoints over the same data):
- `GET /api/alerts` — combines: any `Holding` (any `source`) whose `pnl_pct` ≤ its
  `Threshold.stop_loss_pct`, plus any **live-synced** (`source='api'`) holding whose
  Trajectory unusual-move flag fired (`|z| ≥ 1.5`, task 7's shared function — **not** a
  separate flat ≥3% rule; see planning.md decision #10 for why a flat threshold would
  contradict the reasoning Trajectory itself is built on). Manual holdings never
  contribute a mover alert — no live price data for it to act on (decision #9) — but
  can still trigger a stop-loss alert, since P&L vs. avg cost doesn't need a live feed.

**Post-review fix (2026-07-19):** the initial implementation checked single-stock
concentration per-`Holding`-row instead of aggregating by symbol first — the exact same
shape of bug as the `recent_days`/`thirty_day_days` asymmetry from task 7's review
(one sibling check got the right treatment, the other didn't; here, sector aggregated
correctly one block below while stock didn't). The task's own scope text ("any
`Holding` whose...") technically matched what got built, but was under-specified
relative to the sector check right next to it. Concretely: RELIANCE held at 10% via
PaytmMoney and another 10% via INDmoney is a real 20% single-stock exposure — over the
15% default limit — but neither row alone crosses it, so it went unflagged, defeating
the actual point of the check (planning.md Tier-1 #2). Fixed by aggregating
`market_value_inr` into a `by_symbol` dict first, mirroring the sector block exactly.
Verified with the precise scenario above (10%+10% split across two brokers → flagged
at the correct combined 20%), plus a full regression pass confirming the earlier
single-broker cases still pass unchanged.

## Out of scope

- No settings mutation here — `PUT /api/settings/risk` is task 11.
- No news/rating-change alerts — that's the Tier-3 research feed, out of MVP-1 entirely.

## Acceptance criteria

- With `RiskSettings` at documented defaults (15/30/null/null) and a fixture holding at
  20% of net worth: `/api/risk` flags it.
- With no `RiskSettings` targets set: `/api/risk` still returns the actual India:US
  split, just no drift figure.
- With a fixture holding whose `pnl_pct` is exactly at its stop-loss: `/api/alerts`
  flags it (boundary is inclusive — `pnl_pct <= stop_loss_pct`, matching the sign
  convention in architecture.md's Threshold row).
- A live-synced holding whose today's move produces `|z| ≥ 1.5` is flagged; a calmer
  holding with a larger raw % move but low `|z|` is not — the point of reusing task
  7's flag instead of a flat threshold.
- A manual holding with a large `ltp` vs `close_price` gap (from a manual edit, not a
  live move) never appears as a mover alert, only a possible stop-loss alert.
- ETF concentration/region checks bucket a fixture US-listed ETF under US, not India.
- The same symbol held across two different brokers, each individually under the
  concentration limit, is flagged once its combined exposure crosses the threshold —
  concentration is a per-symbol check, not a per-`Holding`-row one.
