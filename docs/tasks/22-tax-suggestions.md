# 22 — Tax Suggestions

**Depends on:** 21 (PaytmMoney statement import)
**Unlocks:** 25 (deterministic fact tools wrap this for the agent), 27 (daily email digest)

## Goal

Turn the PaytmMoney tax data already sitting in our DB (task 21) into concrete, dated
suggestions — not a tax-lot engine. Per task 20's finding, PaytmMoney already does the FIFO
matching; this task's whole job is reading that output and adding Vantage-specific timing and
framing on top ("book this loss before March 31 — offsets ₹X of your realized gains").

## Scope

New module `bridge-server/app/tax/suggestions.py` (mirrors the `integrations/`/`statements/`
separation-of-concerns pattern), producing a flat list of suggestions from three sources, all
already in the DB:

1. **Loss harvesting** — read the **most recent** `HarvestingSummary`/`HarvestingPosition`
   snapshot (by `as_on_date`). One suggestion per `loss_offset_short_term` /
   `loss_offset_long_term` position: the real `unrealized_pnl` as the harvestable amount,
   framed against the current financial year's end (31 March) — with the number of days
   remaining, so the suggestion carries real urgency instead of a generic nag.
2. **Gain harvesting** — same snapshot's `gain_opportunity_long_term` positions: "book this
   long-term gain — it falls under this year's ₹1.25L tax-free LTCG bucket," using the real
   `unrealized_pnl` and the summary's `lt_gain_harvest_opportunity` headroom.
3. **LTCG-crossing-soon** — for each currently-held PaytmMoney position (`Holding` where
   `source='api'`), find the **earliest imported `Trade` BUY row for that ISIN** and compute
   the long-term crossing date as buy date + 12 calendar months (not a flat 365 days — handles
   month-length correctly). If that date is in the future and within a configurable horizon
   (default 60 days), emit a suggestion naming the real crossing date and days remaining.
   **Explicitly approximate, and honest about it**: this uses the *earliest imported* buy trade
   as a proxy for "the lot that would be sold first under FIFO." If the Trade Book import
   doesn't cover a position's true first purchase (e.g. only a recent date range was uploaded,
   as in task 20/21's sample), the suggestion is simply **not shown** for that holding — never
   fabricated from a partial date range.

New endpoint `GET /api/tax/suggestions` — returns a plain list, each entry: `kind`
(`harvest_loss`/`harvest_gain`/`ltcg_crossing_soon`), `isin`, `scrip_name`, `headline` (the full
reasoning, real numbers inline), `amount_inr` (nullable). No email delivery (task 27) or MCP
wrapping (task 25) yet — this task is the computation plus a plain REST endpoint to verify it
against real data.

**No tax rate percentages asserted in generated text** — LTCG/STCG rates aren't present in the
imported data and citing a specific % risks staleness if rates change; suggestions describe the
tax-treatment *shift* (short-term → long-term), not a rate number.

## Out of scope

- No FIFO ledger over current holdings — see the explicit approximation above. A real per-lot
  ledger would reintroduce exactly the from-scratch tax-lot engineering task 20 found we don't
  need to build.
- No opportunity-cost/benchmark suggestions (needs OHLC/NIFTY — task 25/§5.6, not wired yet).
- No email delivery, no MCP tool wrapping, no frontend page.
- PaytmMoney only, consistent with tasks 20/21.

## Acceptance criteria

- Verified against **real** imported data (re-import fresh/real exports via task 21's
  endpoints, not synthetic fixtures) — every suggested amount matches the source file's own
  figures exactly, not a recomputation that could silently drift from what PaytmMoney reports.
- Loss/gain-harvesting suggestions only appear when the underlying `HarvestingPosition` rows
  exist; an empty harvesting snapshot produces an empty (not fabricated) suggestion list.
- LTCG-crossing-soon only appears for ISINs where a real Trade Book buy row was actually
  imported — confirmed by checking a holding *without* imported trade history produces no
  crossing suggestion, rather than a wrong or default-dated one.
- No hardcoded tax-rate percentage appears anywhere in generated suggestion text.
