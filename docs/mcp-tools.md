# Vantage MCP Tools — Agent Reference

Every tool the **Ask Vantage** panel (and the daily digest's agent section) can call, all
served from bridge-server's own MCP server (`app/vantage_mcp.py`, task 26). None of this is
reachable from outside a spawned `claude` process scoped by
`app/agent_security.py::build_scoped_extra_args` — see
[architecture.md's Security section](./architecture.md#security). Tool names on the wire are
prefixed `mcp__vantage__` (e.g. `mcp__vantage__get_dashboard`); this doc drops the prefix
for readability.

**Read tools never write anything.** **Write tools** are the only ones that change state,
and are only allowlisted when a call site explicitly opts in (`allow_write=True` /
`enable_ui_actions=True` in `build_scoped_extra_args`) — currently just the panel
(`routers/agent_ws.py`).

## Read tools

| Tool | Returns | Notes |
|---|---|---|
| `get_dashboard` | Net worth (INR), per-holding rows, breakdowns, today's move, threshold-breach flags | Same data as `GET /api/dashboard` |
| `get_risk` | Concentration flags, India-vs-US split | Same data as `GET /api/risk` |
| `get_trend(days=30)` | Net-worth time series | Same data as `GET /api/trend` |
| `get_thresholds` | Every holding's stop-loss/target | Same data as `GET /api/thresholds` |
| `get_tax_suggestions` | Harvest-loss/gain + LTCG-crossing-soon suggestions | PaytmMoney-only (task 22) |
| `get_volatility_stops` | Volatility-scaled stop-loss suggestions | Real INDmoney OHLC, India-only, can take ~1–2 min on a cold rate-limit window (task 25) |
| `get_benchmark` | Per-holding return vs. NIFTY 50 / an FD-equivalent | Real OHLC + real imported buy date only — never fabricates a buy date (task 25) |
| `get_status` | Per-broker sync health, mode, token warnings | Same data as `GET /api/status` |
| `get_thesis_history(broker, symbol, include_quarantined=False)` | Every thesis entry for a holding, oldest-first | Task 33. Quarantined entries omitted by default (task 35) |
| `get_decisions(broker=None, symbol=None, include_quarantined=False)` | Every logged call, newest-first | Task 34. Quarantined entries omitted by default (task 35) |
| `get_behavioral_patterns` | `disposition_effect`, `averaging_down`, `win_loss_asymmetry` | Task 37. PaytmMoney-only; a field is `null` where there isn't yet real data, never fabricated |

## Write tools

| Tool | Effect | Notes |
|---|---|---|
| `set_threshold(broker, symbol, stop_loss_pct=None, target_pct=None, notes=None)` | Upserts a `Threshold` row | Only Vantage's own local table — never touches a broker, never places an order. Omitted fields keep their current value |
| `add_thesis_entry(broker, symbol, text, conviction=None)` | Inserts a new `Thesis` row | Append-only — never overwrites a prior entry. `conviction` should be 1–5. Auto-tagged with provenance (task 35), not a caller-supplied argument |
| `log_decision(broker, symbol, headline, reference_price, horizon_days, success_criterion_kind, success_criterion_value, thesis_id=None)` | Inserts a new `DecisionLog` row | `success_criterion_kind` ∈ `price_above` \| `price_below` \| `pct_change_above` \| `pct_change_below`. Auto-tagged with provenance (task 35) |
| `set_decision_status(decision_id, status)` | Updates a `DecisionLog` row's `status` | `status` ∈ `logged` \| `accepted` \| `dismissed` — always explicit, never inferred from conversation |

## UI-action tool

| Tool | Effect | Notes |
|---|---|---|
| `highlight_holding(symbol)` | No data work | Its only purpose is to be a distinctly-named call the frontend recognizes on the WebSocket stream and acts on locally (scroll-to + highlight) — task 29 |

## Things every tool call inherits

- **Read-only to every broker, forever.** No tool anywhere in this server can place, modify,
  or cancel an order — that code doesn't exist in this codebase.
- **Fail-closed scoping.** A spawned agent only ever sees the tools its call site
  explicitly allowlists; anything else is denied outright, not just hidden.
- **Provenance on every write to `Thesis`/`DecisionLog`.** `touched_untrusted_content` is
  set automatically from whether *this session* has called `WebFetch`/`WebSearch`, never
  something the model can claim about itself — see
  [35-memory-poisoning-defenses.md](./tasks/35-memory-poisoning-defenses.md).
- **Grading (`POST /api/decisions/grade`) is REST, not an MCP tool** — deliberately
  on-demand only, to avoid contending with INDmoney's real rate limit; there's no agent tool
  that triggers it.

See [features.md](./features.md) for what these tools look like in actual use through the
panel, and [architecture.md](./architecture.md) for how the whole agent subprocess/security
stack fits together.
