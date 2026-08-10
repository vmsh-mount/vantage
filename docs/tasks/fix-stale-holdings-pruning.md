# Fix: Stale Holdings Never Pruned From a Broker Sync

**Context:** user noticed ICICIBANK listed on the Dashboard despite not holding it, and asked why.

## Root cause, found live

`scheduler._upsert_holding` only ever adds or updates a `Holding` row per (broker, symbol) — it
never removes one. The ICICIBANK row (broker=`indmoney`, real qty/avg-cost figures omitted here
— personal portfolio data, not committed to this public repo) was inserted back when
`INDMONEY_MODE=mock` during early Phase 1 development — confirmed by an **exact** match against
`app/integrations/sample_data.py`'s `INDMONEY_HOLDINGS` fixture (same qty, avg_cost, ltp,
close_price, market_value, pnl_abs, pnl_pct down to the last field). Once real INDmoney
credentials were set up and `INDMONEY_MODE` switched to `live`, the real account's sync simply
never mentioned ICICIBANK again — so the row just sat there, indistinguishable from a real
holding (`source: "api"`, live pricing), quietly inflating displayed net worth by a real, nonzero
amount the whole time.

Independently confirmed live *why* the real sync never touched it: `IndmoneyClient().
fetch_holdings()` genuinely returns **zero** rows right now — the real account's assets are
mutual funds (visible via the INDmoney MCP's `networth_snapshot`), not direct equity, and
`/portfolio/holdings` is equity-only (a known Phase 1 scope gap, not a new finding).

## Fix

`app/scheduler.py`: `_sync_broker` now calls `_prune_stale_holdings(db, broker, live_symbols)`
after a **non-empty** successful fetch — deletes any `source == "api"` `Holding` row for that
broker whose symbol isn't in the fresh response. Deliberately gated on non-empty: an empty
response is more likely a degraded/wrong API call than "you sold everything," and silently
deleting every holding on that basis would be a worse bug than the one being fixed here. Because
of that same guard, this fix's own first real run correctly did **not** prune ICICIBANK
automatically (INDmoney's live response was empty this tick) — removed manually instead, after
independently confirming via a direct client call that the empty response was itself genuine, not
a fluke worth waiting out.

`BrokerSyncResult` gets a `pruned: int` field so `/api/refresh`'s response shows when this fires.

## Out of scope

- Not fixing the equity-only REST scope gap itself (mutual funds not appearing via
  `IndmoneyClient`) — pre-existing, documented Phase 1 limitation, unrelated to this bug.
- No cleanup of orphaned `Threshold`/`Holding.notes` rows for a pruned holding — both are
  already invisible once the `Holding` row is gone (both are only ever surfaced by iterating
  current `Holding` rows), so left alone rather than adding complexity for no visible effect.
  `HoldingSnapshot` rows (trend history) are intentionally untouched either way — a sold
  holding's history shouldn't vanish.

## Verification

- Real `/api/refresh` run against live credentials for both brokers — `pruned: 0` for both,
  correctly, since PaytmMoney's 23 holdings were all still current and INDmoney's response was
  empty (guard correctly held back).
- Independently confirmed the empty INDmoney response was genuine (not transient) via a direct
  `IndmoneyClient().fetch_holdings()` call before manually removing the confirmed-stale row.
- `/api/dashboard`'s `net_worth_inr` before/after: dropped by a real, hand-verified amount
  matching the removed ICICIBANK row's market value plus real intraday price movement on
  PaytmMoney holdings from the `/api/refresh` moments earlier (not a discrepancy) — exact figures
  omitted here, personal portfolio data.
