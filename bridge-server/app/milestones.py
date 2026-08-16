"""Compass (docs/compass-prd.md §6.3, §9): milestone CRUD + pace
projection. Reuses PortfolioSnapshot directly — no new data needed for
net_worth; pnl_pct piggybacks on the same snapshot row (app/scheduler.py's
_write_snapshots), so it's still "no new pipeline," just one more column."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Milestone, PortfolioSnapshot

# How far back to look for a "recent trend" pace estimate. 90 days is
# generous enough to smooth over a single bad week without going so far
# back that an old, no-longer-representative period dominates the
# projection.
PACE_WINDOW_DAYS = 90

SUPPORTED_METRIC_TYPES = ("net_worth", "pnl_pct")

# Which PortfolioSnapshot column backs each metric type. pnl_pct is
# nullable (added after net_worth already had history — see the model's
# own docstring), so every query below has to tolerate a snapshot that
# simply doesn't have this metric yet, the same way a too-short trailing
# window already does.
_SNAPSHOT_FIELD = {
    "net_worth": "total_net_worth_inr",
    "pnl_pct": "total_pnl_pct",
}


def create_milestone(
    db: Session,
    name: str,
    target_value: float,
    target_date: date,
    metric_type: str = "net_worth",
    rationale: str | None = None,
) -> Milestone:
    if metric_type not in SUPPORTED_METRIC_TYPES:
        raise ValueError(f"Unsupported metric_type {metric_type!r}; must be one of {SUPPORTED_METRIC_TYPES}")
    milestone = Milestone(
        name=name, metric_type=metric_type, target_value=target_value, target_date=target_date, rationale=rationale
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


def list_milestones(db: Session) -> list[Milestone]:
    return db.query(Milestone).filter_by(active=True).order_by(Milestone.target_date.asc()).all()


def deactivate_milestone(db: Session, milestone_id: int) -> Milestone | None:
    milestone = db.get(Milestone, milestone_id)
    if milestone is None:
        return None
    milestone.active = False
    db.commit()
    db.refresh(milestone)
    return milestone


def _empty_progress(milestone: Milestone) -> dict:
    return {
        "id": milestone.id,
        "name": milestone.name,
        "metric_type": milestone.metric_type,
        "target_value": milestone.target_value,
        "target_date": milestone.target_date.isoformat(),
        "rationale": milestone.rationale,
        "current_value": None,
        "progress_pct": None,
        "status": "not_enough_data",
        "actual_pace_per_day": None,
        "required_pace_per_day": None,
        "projected_date": None,
        "days_remaining": None,
        "pace_window_days": PACE_WINDOW_DAYS,
    }


def _progress_pct(milestone: Milestone, current_value: float) -> float | None:
    # net_worth's "how far along the absolute target" ratio reads fine
    # because net worth only ever grows from ~0. It doesn't generalize to
    # pnl_pct: a break-even target of 0 would divide by zero, and a
    # negative-to-negative move (e.g. -11% -> -5%) produces a ratio that
    # doesn't read as "progress" at all. current_value/target_value are
    # already in the payload as plain percentage points — that's the
    # honest read for this metric type, not a fabricated ratio.
    if milestone.metric_type != "net_worth":
        return None
    return round(current_value / milestone.target_value * 100, 2) if milestone.target_value else None


def compute_milestone_progress(db: Session, milestone: Milestone) -> dict:
    field = _SNAPSHOT_FIELD[milestone.metric_type]
    latest = (
        db.query(PortfolioSnapshot)
        .filter(getattr(PortfolioSnapshot, field).isnot(None))
        .order_by(PortfolioSnapshot.captured_at.desc())
        .first()
    )
    if latest is None:
        return _empty_progress(milestone)

    current_value = getattr(latest, field)
    today = latest.captured_at.date()
    days_remaining = (milestone.target_date - today).days
    progress_pct = _progress_pct(milestone, current_value)

    if current_value >= milestone.target_value:
        return {
            "id": milestone.id,
            "name": milestone.name,
            "metric_type": milestone.metric_type,
            "target_value": milestone.target_value,
            "target_date": milestone.target_date.isoformat(),
            "rationale": milestone.rationale,
            "current_value": round(current_value, 2),
            "progress_pct": progress_pct,
            "status": "met",
            "actual_pace_per_day": None,
            "required_pace_per_day": None,
            "projected_date": today.isoformat(),
            "days_remaining": days_remaining,
            "pace_window_days": PACE_WINDOW_DAYS,
        }

    # Real decision (docs/compass-prd.md §9): pace from a trailing window,
    # not the whole history — a milestone set long after the account
    # started shouldn't have its projection dragged by ancient, no-longer-
    # representative growth.
    window_start = latest.captured_at - timedelta(days=PACE_WINDOW_DAYS)
    earliest = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.captured_at >= window_start)
        .filter(getattr(PortfolioSnapshot, field).isnot(None))
        .order_by(PortfolioSnapshot.captured_at.asc())
        .first()
    )

    actual_pace_per_day = None
    projected_date = None
    status = "not_enough_data"
    if earliest is not None and earliest.id != latest.id:
        days_elapsed = (latest.captured_at - earliest.captured_at).total_seconds() / 86400
        if days_elapsed > 0:
            actual_pace_per_day = (current_value - getattr(earliest, field)) / days_elapsed
            if actual_pace_per_day > 0:
                days_to_target = (milestone.target_value - current_value) / actual_pace_per_day
                projected_date = today + timedelta(days=round(days_to_target))
                status = "on_pace" if projected_date <= milestone.target_date else "behind"
            else:
                # Flat or shrinking — never reaches the target on this trend,
                # never fabricate a projected date for a pace that doesn't arrive.
                status = "behind"

    required_pace_per_day = (
        (milestone.target_value - current_value) / days_remaining if days_remaining and days_remaining > 0 else None
    )

    return {
        "id": milestone.id,
        "name": milestone.name,
        "metric_type": milestone.metric_type,
        "target_value": milestone.target_value,
        "target_date": milestone.target_date.isoformat(),
        "rationale": milestone.rationale,
        "current_value": round(current_value, 2),
        "progress_pct": progress_pct,
        "status": status,
        "actual_pace_per_day": round(actual_pace_per_day, 2) if actual_pace_per_day is not None else None,
        "required_pace_per_day": round(required_pace_per_day, 2) if required_pace_per_day is not None else None,
        "projected_date": projected_date.isoformat() if projected_date else None,
        "days_remaining": days_remaining,
        "pace_window_days": PACE_WINDOW_DAYS,
    }
