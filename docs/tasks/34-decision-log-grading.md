# 34 — Decision Log With Real Grading

**Depends on:** 33 (`decision_log` has an FK into `thesis`)
**Unlocks:** 36 (the desk note can cite "last time I said X, here's what happened")

## Goal

Half B's second piece, and the one the plan is most explicit about being unbuildable as
originally specced: *"Nothing computes `outcome`. The v1 task only surfaced it."* This task builds
the part v1 skipped — a log entry captured *at the moment a concrete call is made*, with enough
structure that a later job can grade it against reality, not just a table that looks gradeable.

## Scope

**Real decision — grading measures call quality, not user outcome, and says so.** The plan's own
listed confound: *"a dismissed call needs a counterfactual; an accepted one is muddied once you
act manually in the broker."* Vantage cannot observe what you actually did at the broker — it can
only observe what it said and what the market did afterward. Trying to grade "did following this
call make you money" is unbuildable for the same reason v1's `outcome` was unbuildable: nothing
here can see your real trades unless you re-import a Trade Book. So this task deliberately grades
a narrower, honestly-answerable question instead: **was the call's prediction correct**, checked
against real market prices, regardless of whether you accepted, dismissed, or ignored it. That's
weaker than "graded my decisions," but it's true, checkable, and doesn't quietly assume something
Vantage can't know.

**`bridge-server/app/models/decision_log.py`** (new):
```python
class DecisionLog(Base):
    __tablename__ = "decision_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str]
    symbol: Mapped[str]
    thesis_id: Mapped[int | None] = mapped_column(ForeignKey("theses.id"), default=None)
    headline: Mapped[str]                        # the human-readable call, e.g. "consider trimming"
    reference_price: Mapped[float]                # price at the moment of the call
    horizon_days: Mapped[int]
    success_criterion_kind: Mapped[str]             # "price_above" | "price_below" | "pct_change_above" | "pct_change_below"
    success_criterion_value: Mapped[float]
    status: Mapped[str] = mapped_column(default="logged")  # "logged" | "accepted" | "dismissed" — user-set, never inferred
    outcome: Mapped[str | None] = mapped_column(default=None)  # "met" | "not_met" | "inconclusive" — set only by the grading job
    graded_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```
`success_criterion_kind` is a **small closed vocabulary, not free text** — the grading job has to
mechanically evaluate it later, so it can't be an arbitrary sentence.

**`bridge-server/app/vantage_mcp.py`** (modified):
- `log_decision(broker, symbol, headline, reference_price, horizon_days, success_criterion_kind,
  success_criterion_value, thesis_id=None)` — the agent calls this when it makes a concrete,
  checkable recommendation (not every remark — a genuine "here's a call with a real prediction
  attached"). Write-tool, opt-in via `agent_security.py`.
- `set_decision_status(decision_id, status)` — lets you mark a logged call `accepted`/`dismissed`
  yourself; never inferred from conversation text.

**`bridge-server/app/grading.py`** (new) — `grade_pending_decisions(db) -> list[dict]`:
- Queries `DecisionLog` rows where `horizon_days` has elapsed since `created_at` and `outcome`
  is still null.
- Fetches the real price at (or nearest to) the horizon date via the same OHLC path task 25's
  `benchmark.py` already uses — capped by the same real 1-year lookback ceiling task 25 found live
  (documented there, not re-discovered here).
- Evaluates `success_criterion_kind`/`value` against that price, writes `outcome` + `graded_at`.
  `inconclusive` if no OHLC data reaches the horizon date (e.g. the 1-year ceiling), not a
  fabricated `met`/`not_met`.
- Callable on demand (a REST endpoint, `POST /api/decisions/grade`) — **not** on the scheduler.
  Grading touches the INDmoney MCP client's real rate limit (task 25's 30-calls/min finding), so
  an unattended periodic job here risks the same contention task 25 already had to solve once;
  keeping this manual/on-demand for now avoids reproducing that problem for a feature with no
  time-sensitivity of its own (grading a week-old call an hour late costs nothing).

## Out of scope

- No automatic detection of "the agent made a call" from free-form panel conversation — every
  `DecisionLog` row exists because `log_decision` was explicitly called, not inferred.
- No scheduler-driven automatic grading (see above) — on-demand only for now.
- No UI for browsing decision history — agent-only (`get_thesis_history`-style read tool), matching
  task 33's own scope call, revisit together if a UI ever gets built for either.
- No outcome semantics beyond the three states above — no partial credit, no confidence intervals.

## Acceptance criteria

- A real `log_decision` call persists a row with all required fields, and `grade_pending_decisions`
  correctly leaves it ungraded (`outcome: null`) while `horizon_days` hasn't elapsed yet.
- A decision logged with a horizon in the past, and a real, checkable `success_criterion`, gets
  correctly graded against real OHLC data — verified by hand-checking the same price data the
  grading job used, same rigor as task 25's own volatility-figure spot-check.
- A decision whose horizon exceeds what OHLC data can reach (task 25's 1-year ceiling) is graded
  `inconclusive`, not silently skipped or wrongly marked `met`/`not_met`.
- `status` only ever changes via an explicit `set_decision_status` call — confirmed that nothing
  in the grading job or panel conversation flow writes to it.

**Verified live, 2026-08-10.** Against the real running bridge-server, via an actual `mcp` SDK
`ClientSession` over `streamable_http` (same transport the panel uses) plus a real
`POST /api/decisions/grade` call — not code inspection:
- Logged a real `SWIGGY` call with `horizon_days=30` → `POST /api/decisions/grade` correctly left it
  ungraded (`outcome: null`, absent from the `graded` list) since the horizon hadn't elapsed.
- Fetched `SWIGGY`'s real latest OHLC close (₹279.00 on 2026-08-10) directly via the same
  `get_indian_stocks_ohlc` path grading uses, then logged two `horizon_days=0` calls against it —
  `price_above 250` graded `met`, `price_above 300` graded `not_met` — both matching hand
  verification against the real fetched close.
- Logged a call with `created_at` backdated to 2025-03-28 (well before the OHLC lookback actually
  reaches) → graded `inconclusive`, not a fabricated `met`/`not_met` — confirming the real 1y
  ceiling is honored, not just documented.
- `set_decision_status(1, "accepted")` changed `status` only; `outcome`/`graded_at` stayed
  untouched by it, and conversely grading never touched `status` — confirmed independent via a
  final `get_decisions` read-back showing all four rows in the expected end state.
- All test rows deleted afterward — no residue left in the real local DB.
