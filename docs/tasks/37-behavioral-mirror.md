# 37 — Behavioral Mirror

**Depends on:** 21 (Trade Book import — the only real dependency, per planning-phase2.md §7:
*"the mirror needs only task 21 + a surface, not the desk-note generator"*)
**Unlocks:** — (independent; can ship before or after any other Half B piece)

## Goal

Pattern detection over your own real trading history (`Trade`/`RealizedGain`, task 21) — the one
Half B piece the plan explicitly calls out as buildable on its own, not gated behind
thesis/decision-log/quarantine infrastructure.

## Scope

**Real decision — three concrete, mechanically-computable patterns, not a speculative list.**
Chosen because each maps directly to fields task 21's import already provides (PaytmMoney-only,
same scope boundary as tax suggestions and benchmark) — no new data source, no subjective
judgment calls about what counts as a "pattern":

1. **Disposition effect** — average holding period (buy-to-sell gap, in days) for realized winners
   vs. realized losers, from `RealizedGain`. A real, well-known behavioral-finance signal
   (do you hold losers longer than winners, hoping they recover) computable directly from data
   task 21 already parsed.
2. **Averaging-down frequency** — how often a symbol received a second (or later) `BUY` trade
   while its running average cost was already above the then-current price, from `Trade`.
3. **Realized win/loss asymmetry** — win rate (% of closed lots with positive `RealizedGain`) and
   the ratio of average realized gain to average realized loss.

**Real decision — agent-only surface, no new page.** Same call as tasks 33/35: a new Vantage MCP
read tool, `get_behavioral_patterns`, computed on demand from real `Trade`/`RealizedGain` rows —
you ask the panel "what patterns do you see in how I trade" rather than a dashboard card nobody
asked to see unprompted. Consistent with keeping this lean; a UI surface is a real, separate call
to make later if it turns out wanted.

**`bridge-server/app/behavioral.py`** (new) — `compute_disposition_effect(db)`,
`compute_averaging_down(db)`, `compute_win_loss_asymmetry(db)`, each returning real numbers with
the `Trade`/`RealizedGain` rows behind them identifiable (provenance, invariant #5) — no vague
"you seem to..." without a number backing it, matching every other fact-tool in this project.

**`bridge-server/app/vantage_mcp.py`** (modified) — `get_behavioral_patterns()` read tool, wraps
all three functions into one response.

## Out of scope

- No patterns beyond the three above — a small, honest set over a large speculative one.
- No INDmoney trade data — PaytmMoney-only, same explicit scope boundary as tasks 21/22/25's
  benchmark (planning-phase2.md §9).
- No UI page/card (see Scope above).
- No behavioral "score" or gamified framing — three real numbers with their own provenance, not a
  single number that hides how it was computed.

## Acceptance criteria

- All three patterns compute correctly against the real imported Trade Book / Tax P&L data —
  spot-checked by hand against a few real lots, same rigor as task 25's volatility-figure
  spot-check (independently recomputed, not just "the code ran without error").
- A symbol with only one BUY and no further buys correctly shows zero averaging-down events, not
  a division-by-zero or a false positive.
- `get_behavioral_patterns` returns real, current numbers when called live through a real MCP
  session — not fixture data.

**Verified live, 2026-08-10.** Against the real running bridge-server and the real local DB (22
real imported PaytmMoney Trade Book rows; 0 realized-gains rows imported yet in this checkout):
- **Averaging-down**, hand-computed independently from the real 22-row Trade table before running
  the code (grouped by isin, walked chronologically): expected exactly 3 events — `INE00H001014`
  (avg cost 284.15 vs. buy 277.55), `INE040H01021` (avg cost 55.0533 vs. buy 52.65),
  `INE351F01018` (avg cost 19.92 vs. buy 19.21) — and 4 symbols with 2+ BUYs total (one of them,
  `INE364U01010`, correctly produces zero events since both its later buys were at a *higher*
  price than its running average). The real function's output matched this hand computation
  exactly, including the rounded avg-cost figures.
- Five real symbols in the same data have exactly one BUY and no later buys — all correctly
  produced zero averaging-down events (criterion 2), not a crash or a false positive.
- **Disposition effect / win-loss asymmetry**: the real `realized_gains` table is empty in this
  checkout (Tax P&L not imported yet, separately from the Trade Book), so both functions correctly
  returned all-`null`/zero-count results — no fabricated numbers on absent data. To verify the
  arithmetic itself, inserted 5 temporary `RealizedGain` rows with hand-picked, hand-computed
  values (2 winners at 10d/5d holds, 2 losers at 31d/60d holds, 1 breakeven) — the real functions'
  output matched the hand computation exactly (`avg_holding_days_winners: 7.5`,
  `avg_holding_days_losers: 45.5`, `holds_losers_longer: true`, `win_rate: 0.5`,
  `gain_loss_ratio: 1.33`). Test rows deleted immediately after.
- `get_behavioral_patterns` called through a real `mcp` SDK `ClientSession` over `streamable_http`
  (same transport the panel uses) returned output identical to the direct function calls above —
  real, current data, not a fixture.
