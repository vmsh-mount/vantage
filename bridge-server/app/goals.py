"""Compass (docs/compass-prd.md §6.1, §7, §9): Goal CRUD + the three
Tier-1 metric-type calculators, dispatched by metric_type from one entry
point, compute_goal_progress. Each calculator returns a dict shaped for
its own metric type — the storage is generic (one Goal table), the
progress output isn't forced into one shape."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Dividend, Goal, Holding, HoldingSnapshot

SUPPORTED_METRIC_TYPES = ("price_return_pct", "dividend_coverage", "dividend_amount")


def create_goal(
    db: Session,
    name: str,
    metric_type: str,
    target_value: float,
    scope_type: str = "portfolio",
    scope_value: str | None = None,
    comparison: str = "gte",
    period: str = "monthly",
    period_n: int | None = None,
    rationale: str | None = None,
) -> Goal:
    if metric_type not in SUPPORTED_METRIC_TYPES:
        raise ValueError(f"Unsupported metric_type {metric_type!r}; must be one of {SUPPORTED_METRIC_TYPES}")
    goal = Goal(
        name=name,
        metric_type=metric_type,
        scope_type=scope_type,
        scope_value=scope_value,
        comparison=comparison,
        target_value=target_value,
        period=period,
        period_n=period_n,
        rationale=rationale,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def list_goals(db: Session) -> list[Goal]:
    return db.query(Goal).filter_by(active=True).order_by(Goal.created_at.asc()).all()


def deactivate_goal(db: Session, goal_id: int) -> Goal | None:
    goal = db.get(Goal, goal_id)
    if goal is None:
        return None
    goal.active = False
    db.commit()
    db.refresh(goal)
    return goal


def _meets_target(actual: float, comparison: str, target: float) -> bool:
    return actual >= target if comparison == "gte" else actual <= target


def _period_start_date(period: str, today: date, period_n: int | None = None) -> date:
    if period == "monthly":
        return today.replace(day=1)
    if period == "quarterly":
        quarter_start_month = (today.month - 1) // 3 * 3 + 1
        return date(today.year, quarter_start_month, 1)
    if period == "yearly":
        return date(today.year, 1, 1)
    if period == "trailing_n_days":
        # The flexibility dividend_coverage already had via period_n
        # (trailing_n_months, bypassing this function entirely — see its
        # own calculator) but price_return_pct/dividend_amount didn't: a
        # calendar-anchored period can't express "60 days from now" or "a
        # 90-day recovery check" — only "since the 1st of this month/
        # quarter/year." Rolling window, not calendar-aligned.
        return today - timedelta(days=period_n or 30)
    raise ValueError(f"Unsupported period {period!r} for this metric type")


def _holdings_in_scope(db: Session, scope_type: str, scope_value: str | None) -> list[Holding]:
    # source == "api" only — live-synced holdings, same precedent as
    # facts/volatility.py and facts/benchmark.py: manual holdings have no
    # live feed, so a period-over-period return is meaningless for them
    # (Trajectory's own "Static — priced by you" treatment is the same
    # call made elsewhere in this codebase).
    query = db.query(Holding).filter(Holding.source == "api")
    if scope_type == "portfolio":
        pass
    elif scope_type == "sector":
        query = query.filter(Holding.sector == scope_value)
    elif scope_type == "holding":
        if not scope_value or ":" not in scope_value:
            raise ValueError('scope_value for scope_type="holding" must be "broker:symbol"')
        broker, symbol = scope_value.split(":", 1)
        query = query.filter(Holding.broker == broker, Holding.symbol == symbol)
    else:
        raise ValueError(f"Unsupported scope_type {scope_type!r}")
    return query.all()


def compute_price_return_progress(db: Session, goal: Goal) -> dict:
    """Real decision (docs/compass-prd.md §9): per-holding contribution
    attribution, ranked worst-first when missed (best-first when met).
    Simple period-start-vs-now value delta, not a time-weighted return —
    a holding bought mid-period reads as "underperforming" even though
    it's new capital, a documented limitation, not solved here (a real,
    separate upgrade to make later if it proves too noisy in practice)."""
    today = date.today()
    period_start = _period_start_date(goal.period, today, goal.period_n)
    holdings = _holdings_in_scope(db, goal.scope_type, goal.scope_value)

    total_start_inr = 0.0
    total_current_inr = 0.0
    contributions = []
    for h in holdings:
        snapshot = (
            db.query(HoldingSnapshot)
            .filter(
                HoldingSnapshot.broker == h.broker,
                HoldingSnapshot.symbol == h.symbol,
                HoldingSnapshot.captured_at >= period_start,
            )
            .order_by(HoldingSnapshot.captured_at.asc())
            .first()
        )
        if snapshot is None or not snapshot.market_value_inr:
            continue  # no real baseline for this holding this period — excluded, not guessed
        start_value = snapshot.market_value_inr
        current_value = h.market_value_inr
        total_start_inr += start_value
        total_current_inr += current_value
        contributions.append(
            {
                "broker": h.broker,
                "symbol": h.symbol,
                "start_value_inr": round(start_value, 2),
                "current_value_inr": round(current_value, 2),
                "return_pct": round((current_value - start_value) / start_value * 100, 2),
            }
        )

    if total_start_inr <= 0:
        return _goal_result(goal, status="not_enough_data", actual_value=None, extra={"contributions": []})

    actual_pct = (total_current_inr - total_start_inr) / total_start_inr * 100
    met = _meets_target(actual_pct, goal.comparison, goal.target_value)

    for c in contributions:
        c["contribution_pp"] = round((c["current_value_inr"] - c["start_value_inr"]) / total_start_inr * 100, 2)
    contributions.sort(key=lambda c: c["contribution_pp"], reverse=met)

    return _goal_result(
        goal,
        status="met" if met else "missed",
        actual_value=round(actual_pct, 2),
        extra={"period_start": period_start.isoformat(), "contributions": contributions},
    )


def _trailing_months(n: int, today: date) -> list[tuple[int, int]]:
    """Oldest-first list of (year, month) for the trailing n months,
    including the current month."""
    months = []
    for i in range(n):
        month_index = today.month - 1 - i
        year = today.year + month_index // 12
        month = month_index % 12 + 1
        months.append((year, month))
    months.reverse()
    return months


def compute_dividend_coverage_progress(db: Session, goal: Goal) -> dict:
    n = goal.period_n or 6
    today = date.today()
    months = _trailing_months(n, today)

    dividends = db.query(Dividend).all()
    covered_months = {(d.payment_date.year, d.payment_date.month) for d in dividends}

    coverage = [{"year": y, "month": m, "covered": (y, m) in covered_months} for y, m in months]
    covered_count = sum(1 for c in coverage if c["covered"])
    gap_months = [f"{c['year']}-{c['month']:02d}" for c in coverage if not c["covered"]]

    met = _meets_target(covered_count, goal.comparison, goal.target_value)
    return _goal_result(
        goal,
        status="met" if met else "missed",
        actual_value=covered_count,
        extra={"window_months": n, "coverage": coverage, "gap_months": gap_months},
    )


def compute_dividend_amount_progress(db: Session, goal: Goal) -> dict:
    today = date.today()
    period_start = _period_start_date(goal.period, today, goal.period_n)
    current_total = sum(
        d.amount_inr for d in db.query(Dividend).filter(Dividend.payment_date >= period_start).all()
    )

    # Prior period, for trend context (docs/compass-prd.md §9: "whether a
    # shortfall is a one-off or a trend").
    prior_period_start = _period_start_date(goal.period, period_start - timedelta(days=1), goal.period_n)
    prior_total = sum(
        d.amount_inr
        for d in db.query(Dividend)
        .filter(Dividend.payment_date >= prior_period_start, Dividend.payment_date < period_start)
        .all()
    )

    met = _meets_target(current_total, goal.comparison, goal.target_value)
    return _goal_result(
        goal,
        status="met" if met else "missed",
        actual_value=round(current_total, 2),
        extra={"period_start": period_start.isoformat(), "prior_period_total_inr": round(prior_total, 2)},
    )


def _goal_result(goal: Goal, status: str, actual_value: float | None, extra: dict) -> dict:
    return {
        "id": goal.id,
        "name": goal.name,
        "metric_type": goal.metric_type,
        "scope_type": goal.scope_type,
        "scope_value": goal.scope_value,
        "comparison": goal.comparison,
        "target_value": goal.target_value,
        "period": goal.period,
        "rationale": goal.rationale,
        "actual_value": actual_value,
        "status": status,
        **extra,
    }


_CALCULATORS = {
    "price_return_pct": compute_price_return_progress,
    "dividend_coverage": compute_dividend_coverage_progress,
    "dividend_amount": compute_dividend_amount_progress,
}


def compute_goal_progress(db: Session, goal: Goal) -> dict:
    calculator = _CALCULATORS.get(goal.metric_type)
    if calculator is None:
        return _goal_result(goal, status="not_enough_data", actual_value=None, extra={"error": f"Unsupported metric_type {goal.metric_type!r}"})
    return calculator(db, goal)
