# 25 — Deterministic Fact Tools

**Depends on:** 22 (tax suggestions), 24 (INDmoney MCP client — the market-data path)
**Unlocks:** 26 (Vantage MCP server exposes these as agent-callable tools)

## Goal

Build the two genuinely *new* deterministic computations the plan calls for — volatility-scaled
stop-loss suggestions and benchmark/opportunity-cost — using bridge-server's own INDmoney MCP
client (task 24) to fetch real OHLC. Per invariant #5 (planning-phase2.md §2.5), every number
these produce carries a reference to what produced it.

**Scope decision on "tax" and "concentration" (also named in the plan's task 25 row):** neither
is rebuilt here. Task 22's tax suggestions already cite the exact PaytmMoney report row behind
every number; Phase 1's `/api/risk` concentration flags are already fully deterministic from
`Holding` rows, readable in `app/routers/risk.py`. Both already satisfy invariant #5's *intent*
(a human can see exactly where every number comes from) without a formal provenance field.
Retrofitting one onto two already-shipped, working schemas isn't worth the churn right now —
that's better done when task 26+'s agent layer actually needs to *programmatically* distinguish
sourced from unsourced numbers, not preemptively. This task's new work — vol-stops and
benchmark — gets provenance built in from day one, since it's new.

## Scope

**Real constraints discovered live before writing any code** (not assumed):
- `get_indian_stocks_ohlc`'s `lookback` parameter is a fixed enum — `1d`, `7d`, `14d`, `1y` —
  **`1y` is the actual ceiling**, and the response still reports `has_more_data: true` at that
  point, meaning older history genuinely isn't reachable through this tool at all, not just
  paginated. This directly limits benchmark/opportunity-cost for holdings bought over a year
  ago (real cases exist — task 20's Tax P&L sample showed lots from 2021–2022).
- `lookup_ind_keys` resolves a stock/index **name** to one or more candidate `ind_key`s (fuzzy —
  e.g. "RELIANCE" returned three companies). There is no ISIN-based lookup tool. This task uses
  the holding's symbol as the query and takes the first match — a **documented, honest
  limitation** (name-based, not ISIN-verified), not silently assumed precise.
- Indices resolve through the same `lookup_ind_keys` call as stocks (confirmed: NIFTY 50 →
  `INDI00012`, an `INDI`-prefixed key, via the same `filter_type=IN_STOCKS` query) — no separate
  index endpoint needed.
- INDmoney's MCP server enforces a real **global rate limit — 30 calls/min** — confirmed live via
  the exact error envelope it returns instead of tool data: `{"error": "rate_limit_exceeded",
  "retry_after_seconds": N, ...}`. `volatility-stops` costs 2 calls/holding (lookup + OHLC); with
  24 real holdings that's up to 48 calls, comfortably over the limit on a single request — this
  isn't a hypothetical edge case, it reproduced on the very first real end-to-end run. Two bugs
  found and fixed in `indmoney_mcp.py`, not worked around: (1) the error envelope was being
  silently unwrapped and handed to callers as if it were real data — `lookup_ind_keys` callers
  doing `matches[0]` on the error dict raised a confusing `KeyError: 0` instead of a clear
  signal; `call_tool` now recognizes this shape and raises `RateLimitExceeded`. (2) that
  exception, raised from inside the nested `streamablehttp_client`/`ClientSession` context
  managers, comes back wrapped in nested `BaseExceptionGroup`s from anyio's internal TaskGroups
  (the same class of issue task 24 hit once with the SDK's own error handling) — `call_tool` uses
  `except* RateLimitExceeded` plus a recursive unwrap to find the real exception at any nesting
  depth, then retries honoring the server's own `retry_after_seconds` (capped at 3 retries).
  Batching `lookup_ind_keys` across multiple names was evaluated as an alternative (would cut 24
  calls to 1) and rejected: verified live that batched responses come back as one flat merged
  list with no per-name grouping, so there's no reliable way to attribute a match back to the
  symbol that produced it — silently misattributing matches would be worse than the slower,
  correctly-attributed one-call-per-symbol approach this task already documents above.

**`bridge-server/app/facts/volatility.py`** — vol-scaled stop-loss suggestions:
- For each currently-held PaytmMoney holding (`Holding.source == 'api'`), resolve its symbol to
  an `ind_key`, fetch `1y` daily OHLC, and compute the standard deviation of daily % returns over
  the **trailing ~60 calendar days** of that response (sliced client-side — the tool has no
  30/60/90-day option, so the full year is fetched and trimmed rather than over-fetched data
  being wasted on a too-short 14-day sample).
- Suggested stop = **−2.5× that volatility**, bounded to **[−25%, −5%]** (a stock swinging so
  little that 2.5× volatility would suggest tighter than −5% still gets floored at −5% — a
  degenerately tight stop isn't useful; one swinging so much it would suggest looser than −25%
  gets capped there too, since that's arguably not a stop-loss anymore).
- Output per holding: `suggested_stop_loss_pct`, the real `volatility_pct` behind it, the
  holding's *current* `Threshold.stop_loss_pct` if one exists (so the suggestion reads as a
  comparison, not a cold number), reasoning text in the same style as task 22 ("ZAGGLE swings
  ~2.4%/day — a −7% stop ≈ three bad days"), and provenance (`data_source`, `as_of`, `ind_key`
  used).

**`bridge-server/app/facts/benchmark.py`** — opportunity-cost:
- For each currently-held PaytmMoney holding **with an imported Trade Book buy row for its ISIN**
  (reusing task 22's exact pattern — silently skip holdings with no imported trade history,
  never fabricate a buy date).
- The holding's own return: `Holding.pnl_pct` (already computed from `avg_cost`; noted
  limitation — this blends multiple buy lots if there are several, it is not a single-lot return).
- NIFTY 50's return over the same window, **capped at whatever the 1-year OHLC ceiling actually
  allows** — if the real holding period exceeds a year, the comparison window is explicitly
  labelled "over the last year," never silently presented as "since you bought it" when it isn't.
- An FD-equivalent return over the identical window, simple annualized interest at a
  configurable rate (default 7%, matching common current FD rates — not fetched live, no free
  reliable source for this; documented as a static assumption).
- Output per holding: the three returns side by side, a flag when the holding underperformed
  both, and provenance for the OHLC-derived figure.

**New endpoints** (`bridge-server/app/routers/facts.py`): `GET /api/facts/volatility-stops`,
`GET /api/facts/benchmark`. Plain REST, matching this project's established pattern of a real
verifiable endpoint per backend feature — task 26 wraps these as MCP tools later; this task
proves the computation is correct against real data first.

## Out of scope

- No provenance retrofit onto task 22 or `/api/risk` (see Scope Decision above).
- No session reuse / caching for the INDmoney MCP client — task 24's connect-per-call remains;
  ~24 sequential OHLC fetches per request is a known, accepted performance characteristic for
  now, not a blocker. Optimize later if it's actually too slow in practice. (Rate-limit-aware
  retry/backoff *was* added to `call_tool` — see above — but that's a correctness fix for a
  request that would otherwise crash, not the connect-per-call → session-reuse optimization
  still deferred here. As a direct consequence, `volatility-stops` now genuinely takes ~2
  minutes end-to-end on a cold rate-limit window — verified live, not estimated — since 48
  calls against a 30/min ceiling forces one real backoff pause. Acceptable for now since this
  task is about correctness against real data, not latency.)
- No ISIN-verified stock resolution — no such tool exists on the INDmoney MCP surface; the
  name-based fuzzy match is the honest ceiling here, not a gap to paper over.
- No F&O, no US-holding coverage (India-only, per planning-phase2.md §3).

## Acceptance criteria

- Both endpoints run against real current holdings and real OHLC pulled live through task 24's
  client — not fixtures.
- A volatility suggestion's `volatility_pct` is independently recomputable by hand from the same
  OHLC window and matches (spot-checked, not just "the code ran without error").
- A benchmark suggestion for a holding bought over a year ago is labelled as covering the
  available window, not silently claiming full-period coverage it can't actually provide.
- A holding with no imported Trade Book history produces no benchmark entry — confirmed, not
  assumed.
- Every value in both responses traces to a real tool call or a documented static assumption
  (the FD rate) — nothing is asserted without a stated source.
