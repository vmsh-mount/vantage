# Compass — PRD

**Status:** proposed, not yet built. One consolidated document — see [README.md](../README.md)
for how this relates to the rest of the (already-shipped) system.

## 1. Summary

Vantage tells you what you have. It doesn't tell you **whether that's what you actually
wanted**, or **what to do about the gap**. Compass is a goal-setting and diagnosis feature:
you declare intentions about how your portfolio should behave, Vantage tracks real progress
against them, and explains *why* a goal was or wasn't met using real data — not a pass/fail
badge.

## 2. Problem

Origin conversation (paraphrased, generalized): build a portfolio spread across several
sectors with reliable dividend income, using a monthly return figure as an example of "am I
on track." Stripped of the specific numbers, the underlying want is:

> I have intentions for my portfolio that aren't captured anywhere. I want to declare them,
> see real progress against them, and when I'm off track, understand *why* — not just see a
> red number.

**Revision note:** the first draft of this PRD over-indexed on the literal examples given
(sector count, one return figure, dividends) and under-surveyed what Vantage already computes
that could become a trackable target. §3 below is a real product-level brainstorm — grouped by
the actual question a person is asking — done before finalizing scope, not after.

## 3. What people actually track, periodically — the full map

Grouped by the real question behind each one. Marked with what it needs:
**[existing]** — Vantage already computes this, a target is just a threshold on top;
**[existing table, new angle]** — the raw data exists, nothing reads it this way yet;
**[new]** — genuinely new data (only dividends, confirmed in §8).

**"Is my money growing the way I want?"**
- Portfolio-wide return over a period, not just per-sector/holding **[existing]**
  (`Holding.pnl_pct`/`HoldingSnapshot`) — the first draft skipped the portfolio-wide case
  entirely and only scoped to sector/holding.
- Beating a benchmark (NIFTY / an FD-equivalent) **[existing]** — `facts/benchmark.py`
  computes this today; it's just never framed as a settable target.
- Reaching a net-worth milestone by a date **[existing]** (`PortfolioSnapshot` history). The
  first draft explicitly excluded this as "financial planning" — wrong call, this is the most
  natural portfolio target there is and needs zero new data.

**"Am I taking the right amount of risk?"**
- Max drawdown from peak **[existing table, new angle]** (`PortfolioSnapshot`).
- Single-stock/sector concentration ceiling **[existing]** — this is **already
  `RiskSettings`**. The first draft invented a parallel concept and never once referenced it.
- India:US allocation drift **[existing]** — **already `RiskSettings.target_india_pct/
  target_us_pct`**, also unreferenced in the first draft.

**"Is my portfolio actually shaped the way I want?"**
- Sector mix — what the first draft had, but as a *count*, not a *composition*.
- Market-cap mix (large/mid/small) **[existing table, new angle]** — INDmoney's own data
  already carries this breakdown.
- Asset-class mix (equity vs. cash/debt-like).

**"Is this generating income the way I want?"**
- Dividend coverage and amount **[new]** — the one piece needing real new plumbing, which is
  exactly why it dominated the first draft. It's one target family among many, not the
  centerpiece.

**"Am I actually behaving the way I intend to?"**
- Regular contribution/investing discipline ("invested ≥ ₹X this month") **[existing table,
  new angle]** (`Trade`, sum of `BUY` value in the period) — arguably more commonly tracked in
  practice than an aggressive monthly return figure.
- Trading turnover / overtrading discipline **[existing]** — task 37's behavioral mirror
  already computes this shape of thing.
- Realized win rate improving over time **[existing]** — same source
  (`compute_win_loss_asymmetry`).

**"Am I using the tax efficiency available to me?"**
- Realized-loss harvesting actually executed this FY, LTCG-bucket utilization **[existing
  table, new angle]** — `RealizedGain` has the real numbers; task 22 only ever *suggests*,
  never checks *whether you acted*.

## 4. Goals (of this PRD)

- Cover the map in §3 with an architecture that fits its real shapes — not one generic table
  forced to represent three structurally different kinds of goal (see §5).
- Reuse every existing Vantage computation (`RiskSettings`, `facts/benchmark.py`,
  `behavioral.py`, `RealizedGain`, `Trade`, `PortfolioSnapshot`) rather than re-deriving
  anything already correct and verified elsewhere in this codebase.
- A real, always-visible page — the user was explicit about wanting "a section," not something
  you only learn by asking the agent panel.
- Diagnosis, not just a status badge, wherever "why" is answerable from real data.
- Recommendations name gaps in the user's own real portfolio; never a specific security to buy
  — no tool anywhere in this codebase has ever produced that kind of output.

## 5. Non-goals

- No stock screener or security recommendation engine (see above — a hard boundary, not a
  soft preference).
- No automated dividend import — confirmed live, no broker API exposes it (§8).
- No true financial-planning engine (retirement corpus modeling, inflation-adjusted goals,
  Monte Carlo projections) — the net-worth milestone in §7 is a simple pace-vs-target
  projection off real historical data, not a planning model.
- No multi-currency, multi-user, or mobile — same boundaries as the rest of Vantage.
- No new notification channel — surfaces are the Compass page, one digest line, and the
  existing Ask Vantage panel.

## 6. Three shapes, not one table

The first draft's single scalar `target_value` table couldn't honestly represent everything
in §3. Three real shapes:

1. **Scalar goals** — a single number checked against a single target: return %, dividend
   amount/coverage, win rate, monthly contribution, realized-loss-harvested amount, max
   drawdown. One table, `Goal`, fits all of these.
2. **Allocation/mix goals** — a target *composition* across several buckets summing to
   ~100% (sector, market-cap, asset-class, region), not one number. Forcing this into scalar
   goals is what produced the first draft's awkward "5 sectors, each ≥8%" hack. Gets its own
   table, `AllocationTarget`.
3. **Milestone goals** — a target reached by a *date*, not a recurring period (net worth by a
   deadline). Needs a target date and a pace projection, not a period. Gets its own table,
   `Milestone`.

### 6.1 `Goal` — scalar targets

```python
class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    metric_type: Mapped[str] = mapped_column()  # see §7 — extensible enum
    scope_type: Mapped[str] = mapped_column()  # "portfolio" | "sector" | "holding"
    scope_value: Mapped[str | None] = mapped_column(default=None)
    comparison: Mapped[str] = mapped_column(default="gte")  # "gte" | "lte"
    target_value: Mapped[float] = mapped_column()
    period: Mapped[str] = mapped_column(default="monthly")
    # "point_in_time" | "monthly" | "quarterly" | "yearly" | "trailing_n_months"
    period_n: Mapped[int | None] = mapped_column(default=None)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

### 6.2 `AllocationTarget` — composition targets

```python
class AllocationTarget(Base):
    __tablename__ = "allocation_targets"
    id: Mapped[int] = mapped_column(primary_key=True)
    dimension: Mapped[str] = mapped_column()  # "sector" | "market_cap" | "asset_class" | "region"
    bucket: Mapped[str] = mapped_column()  # e.g. "Technology", "Large Cap", "India"
    target_pct: Mapped[float] = mapped_column()
    tolerance_pct: Mapped[float] = mapped_column(default=5.0)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

One row per bucket within a dimension — e.g. five rows with `dimension="sector"` and
`target_pct` summing to 100 directly expresses "spread across 5 sectors," and does it *better*
than the first draft's count+floor hack: a bucket with 0% actual allocation against a real
target is a specific, named gap ("Healthcare: target 15%, you hold 0%"), not just a number
short of a count.

**Real decision — `region` here can absorb `RiskSettings.target_india_pct/target_us_pct`
later, not required now.** They're the same shape (a 2-bucket allocation target). Noting the
overlap rather than silently duplicating it, as the first draft did — but not migrating a
working, shipped feature as a side effect of this PRD. A real, separate follow-up if it turns
out wanted.

**Real decision — `tolerance_pct`, not a bare comparison direction.** A single number per
bucket with a tolerance band naturally covers both "you're underweight" and "you're
overweight" from one row, which is what actually generalizes `RiskSettings`' existing ceiling
concept and this feature's floor concept into one representation — cleaner than the scalar
`Goal`'s `gte`/`lte` split, which doesn't fit a composition target at all.

### 6.3 `Milestone` — deadline-based targets

```python
class Milestone(Base):
    __tablename__ = "milestones"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    metric_type: Mapped[str] = mapped_column(default="net_worth")
    target_value: Mapped[float] = mapped_column()
    target_date: Mapped[date] = mapped_column()
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

Progress: current value, required pace (`(target - current) / days_remaining`), actual recent
pace (trend over a trailing window of `PortfolioSnapshot` history), on-pace or not, and a
projected date at the current trend — explicitly caveated as "assumes the recent trend
continues," never presented as a guarantee.

## 7. Metric types — tiered by build cost, not by importance

Every `Goal.metric_type` dispatches to its own calculator. Split into what needs genuinely new
plumbing vs. what's a thin wrapper over something Vantage already computes correctly —
because the second group is a real, near-zero-cost extension of the same dispatcher, not a
reason to scope-creep v1.

**Tier 1 — build in v1** (either genuinely new, or the clearest expression of the origin ask):

| `metric_type` | Measures | Source |
|---|---|---|
| `price_return_pct` | % price return, scope-able to portfolio/sector/holding | `HoldingSnapshot` (existing) |
| `dividend_coverage` | Fraction of trailing N months with ≥1 dividend logged | new `Dividend` log |
| `dividend_amount` | Total dividend income vs. a target figure | new `Dividend` log |

Plus `AllocationTarget` (§6.2, all dimensions) and `Milestone` (§6.3, net worth) — both ship
in v1; they're what actually answer "spread across sectors" and "make consistent progress"
properly, more so than an extra `Goal` metric type would.

**Tier 2 — same dispatcher, one enum value + one calculator each, ship if/when wanted:**

| `metric_type` | Measures | Source |
|---|---|---|
| `benchmark_excess_return_pct` | Return vs. NIFTY 50 / FD-equivalent | `facts/benchmark.py` (existing) |
| `win_rate_pct` | Realized win rate | `behavioral.py` (existing) |
| `monthly_contribution_inr` | Real ₹ invested (sum of `BUY` trades) in the period | `Trade` (existing) |
| `realized_loss_harvested_inr` | Real realized losses booked this FY | `RealizedGain` (existing) |
| `max_drawdown_pct` | Peak-to-trough decline over a window | `PortfolioSnapshot` (existing) |

Named explicitly so the architecture doesn't get redesigned the first time one of these is
actually wanted — not built speculatively now, since nothing in the origin conversation asked
for them yet.

## 8. Dividends: real constraint, verified live

Unchanged from the original research — still the one genuinely new data source in this PRD,
even though it's no longer the centerpiece:

- **INDmoney MCP** — `get_indian_stocks_details` (no `dividends` segment exists),
  `networth_holdings`, `networth_snapshot`: no dividend/income field in any of the three,
  checked against the real linked account.
- **PaytmMoney Trading API** — the official SDK's complete method surface has no
  dividend/corporate-actions endpoint. PaytmMoney's app tracks dividends in a "Corporate
  Actions" section, but only as an in-app view, never via the API bridge-server integrates
  with.
- **`funds_summary(config=True)`** — the one lead that looked like a transaction ledger,
  called live against the real account: it's balance + fund-transfer validation limits, not a
  ledger.

```python
class Dividend(Base):
    __tablename__ = "dividends"
    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    symbol: Mapped[str] = mapped_column()
    amount_inr: Mapped[float] = mapped_column()
    payment_date: Mapped[date] = mapped_column()
    notes: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

## 9. Diagnosis ("what happened")

- **`price_return_pct`**: per-holding contribution attribution — `(period-start weight) ×
  (own period return)`, summed ≈ the scope's total return (a documented approximation, not
  time-weighted — a real upgrade to make later if it proves too noisy in practice). Ranked
  worst-contributor-first when missed.
- **`AllocationTarget`**: per-bucket actual vs. `target_pct ± tolerance_pct` — every bucket
  labeled `on_target` / `underweight` / `overweight`, including a target bucket at 0% actual
  (the real, named gap a plain sector-count check would only show as "one short").
- **`Milestone`**: required pace vs. actual recent pace, in plain terms ("at your last 3
  months' rate, you'd reach this around [date]").
- **`dividend_coverage`/`dividend_amount`**: named gap months, trend vs. the prior period.
  No inference of *why* a month had no dividend — the log has no link back to `Trade` history
  to support that reliably.

No security-level recommendation anywhere in any of the above — restated because it's the
easiest place for this feature to drift, and no tool in this codebase has ever produced one.

## 10. Surfaces

1. **Compass page** (`deck-app/src/pages/Compass.tsx`) — sections for Milestones, Allocation
   Targets (grouped by dimension), and Goals. Each shows target, real current value, status,
   and inline diagnosis when off-target. Forms to create/edit/deactivate each.
2. **One digest line** — a single deterministic summary added to the existing daily email
   (e.g. "2 of 3 allocation targets on target, net worth milestone on pace"). Not a new
   agent-authored section (task 36 already added one). Omitted entirely with nothing
   configured.
3. **Ask Vantage panel** — new read-only MCP tools for conversational drill-down (below).

## 11. API surface

| Endpoint | Purpose |
|---|---|
| `GET/POST/PUT/DELETE /api/goals` | CRUD for scalar `Goal` rows |
| `GET/POST/PUT/DELETE /api/allocation-targets` | CRUD for `AllocationTarget` rows |
| `GET/POST/PUT/DELETE /api/milestones` | CRUD for `Milestone` rows |
| `GET/POST/PUT/DELETE /api/dividends` | CRUD for the manual `Dividend` log |
| `GET /api/compass/summary` | Every active goal/target/milestone's current status in one call |

New MCP read tools: `get_compass_summary` (mirrors `get_behavioral_patterns`' one-call bundle
of several computations), plus `get_goal_progress`/`get_allocation_progress`/
`get_milestone_progress` for conversational drill-down into one item's diagnosis.

## 12. Build order

1. `Dividend` log + CRUD — no dependencies, needed by two `Goal` metric types.
2. `AllocationTarget` model + CRUD + calculator — reuses existing breakdown-by-dimension logic
   already in `get_dashboard`/INDmoney data, so this is mostly wiring, not new math. Ships the
   clearest version of the origin "spread across sectors" ask.
3. `Milestone` model + CRUD + pace calculator — reuses `PortfolioSnapshot` directly.
4. `Goal` model + CRUD + the three Tier-1 calculators (`price_return_pct` +
   attribution, `dividend_coverage`, `dividend_amount`).
5. Compass page, assembling 1-4 into one view.
6. `get_compass_summary` + drill-down MCP tools + the digest line — last, since it composes
   over everything above.
7. Tier-2 metric types (§7) — separate, later follow-ups; each is one calculator function
   plus one enum value against the dispatcher this task already builds, not a new feature.

## 13. Acceptance criteria

- Each Tier-1 metric type, plus `AllocationTarget` and `Milestone`, computes correctly against
  real data, matching a hand calculation from the same underlying rows — same rigor as every
  other fact-tool in this codebase.
- An `AllocationTarget` bucket with real 0% actual allocation against a real target is
  reported as `underweight` with the correct gap, not silently omitted.
- A `Milestone`'s pace projection matches a hand calculation from the same
  `PortfolioSnapshot` rows.
- A `price_return_pct` goal with no snapshot history at the period start returns
  `not_enough_data`, never a fabricated 0%.
- A missed `price_return_pct` goal's attribution sums back to (approximately) the scope's own
  total return.
- The digest line appears only when ≥1 item is configured, matches `GET /api/compass/summary`
  for the same DB state, verified via a real send.
- A real panel conversation asking "why" about a specific missed item produces an answer
  backed by a visible drill-down tool call.
- No recommendation anywhere names a specific security to buy — checked by inspection of every
  code path that generates recommendation text.

## 14. Open questions

- Exact "on track" / "at risk" / "missed" thresholds for the Compass page's visual status
  (e.g. 95%-of-target vs. 10%-of-target shouldn't render identically) — a UX call for
  implementation time, not blocking the data model above.
- Whether `Goal`/`Milestone`'s `name` field is free text or auto-generated from its own
  fields — not load-bearing enough to resolve before implementation starts.
- Whether any Tier-2 metric type should actually move to Tier 1 before build starts — flagged
  here rather than decided unilaterally, since it changes v1's scope.
