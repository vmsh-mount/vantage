"""Task 34 (planning-phase2.md §7.1): on-demand grading of decision-log
calls against real market prices. Grades **call quality** only — was the
prediction correct — never user outcome; see
docs/tasks/34-decision-log-grading.md's Scope for why "did following this
call make you money" is unbuildable the same way v1's `outcome` was.

Reuses task 25's INDmoney OHLC path (app.facts.volatility's symbol
resolution and app.integrations.indmoney_mcp.call_tool), including its
real, live-confirmed 1-year lookback ceiling: a decision whose horizon date
falls before what that window reaches is graded `inconclusive`, never
guessed at.

On-demand only (POST /api/decisions/grade), never scheduler-driven — task
25's own live testing found a real 30-calls/min INDmoney rate limit, and an
unattended periodic grading job risks the same contention that had to be
solved once already for a feature with no time-sensitivity of its own
(grading a week-old call an hour late costs nothing)."""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.facts.volatility import _resolve_ind_key
from app.integrations.indmoney_mcp import call_tool
from app.models import DecisionLog
from app.models._util import utcnow


def _price_on_or_after(candles: list[dict], target_date: date) -> tuple[date, float] | None:
    """Earliest candle at/after target_date. None if target_date falls
    before the OHLC history actually reaches back to — the real 1y
    lookback ceiling task 25 already found live — never extrapolated past
    what the data actually covers."""
    if not candles:
        return None
    parsed = sorted((datetime.fromisoformat(c["datetime_ist"]).date(), c["close"]) for c in candles)
    if target_date < parsed[0][0]:
        return None
    on_or_after = [p for p in parsed if p[0] >= target_date]
    return on_or_after[0] if on_or_after else parsed[-1]


def _evaluate_criterion(kind: str, value: float, reference_price: float, graded_price: float) -> bool:
    if kind == "price_above":
        return graded_price > value
    if kind == "price_below":
        return graded_price < value
    if kind == "pct_change_above":
        return (graded_price - reference_price) / reference_price * 100 > value
    if kind == "pct_change_below":
        return (graded_price - reference_price) / reference_price * 100 < value
    raise ValueError(f"Unknown success_criterion_kind: {kind!r}")


def _serialize(decision: DecisionLog) -> dict:
    return {
        "id": decision.id,
        "broker": decision.broker,
        "symbol": decision.symbol,
        "thesis_id": decision.thesis_id,
        "headline": decision.headline,
        "reference_price": decision.reference_price,
        "horizon_days": decision.horizon_days,
        "success_criterion_kind": decision.success_criterion_kind,
        "success_criterion_value": decision.success_criterion_value,
        "status": decision.status,
        "outcome": decision.outcome,
        "graded_at": decision.graded_at,
        "created_at": decision.created_at,
    }


async def grade_pending_decisions(db: Session) -> list[dict]:
    """Grades every DecisionLog row whose horizon has elapsed and that
    isn't graded yet. A row whose horizon hasn't elapsed is left untouched
    (not an error, not skipped forever — it's picked up on a later call
    once its date arrives)."""
    now = utcnow()
    pending = db.query(DecisionLog).filter(DecisionLog.outcome.is_(None)).all()
    graded: list[dict] = []

    for decision in pending:
        horizon_date = (decision.created_at + timedelta(days=decision.horizon_days)).date()
        if horizon_date > now.date():
            continue

        ind_key = await _resolve_ind_key(decision.symbol)
        priced = None
        if ind_key is not None:
            ohlc = await call_tool(
                "get_indian_stocks_ohlc", {"ind_key": ind_key, "interval": "1day", "lookback": "1y"}
            )
            priced = _price_on_or_after(ohlc.get("candles", []), horizon_date)

        if priced is None:
            decision.outcome = "inconclusive"
        else:
            _, graded_price = priced
            met = _evaluate_criterion(
                decision.success_criterion_kind,
                decision.success_criterion_value,
                decision.reference_price,
                graded_price,
            )
            decision.outcome = "met" if met else "not_met"

        decision.graded_at = now
        db.commit()
        db.refresh(decision)
        graded.append(_serialize(decision))

    return graded
