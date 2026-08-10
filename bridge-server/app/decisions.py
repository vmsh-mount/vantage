"""Task 34 (planning-phase2.md §7.1): persistence for concrete, checkable
calls — kept separate from app/vantage_mcp.py so it's testable without
going through an MCP tool call, matching app/thesis.py's own split.
Grading itself lives in app/grading.py, not here — this module only ever
inserts a DecisionLog row or flips its user-set `status`; it never writes
`outcome`/`graded_at`.

Task 35 added run_session_id/touched_untrusted_content/reviewed — see
models/decision_log.py's own comment on those columns and
app/run_context.py's docstring for the full provenance/quarantine story."""

from sqlalchemy import and_, not_
from sqlalchemy.orm import Session

from app.models import DecisionLog

VALID_STATUSES = ("logged", "accepted", "dismissed")


def log_decision(
    db: Session,
    broker: str,
    symbol: str,
    headline: str,
    reference_price: float,
    horizon_days: int,
    success_criterion_kind: str,
    success_criterion_value: float,
    thesis_id: int | None = None,
    run_session_id: str = "",
    touched_untrusted_content: bool = False,
) -> DecisionLog:
    decision = DecisionLog(
        broker=broker,
        symbol=symbol,
        headline=headline,
        reference_price=reference_price,
        horizon_days=horizon_days,
        success_criterion_kind=success_criterion_kind,
        success_criterion_value=success_criterion_value,
        thesis_id=thesis_id,
        run_session_id=run_session_id,
        touched_untrusted_content=touched_untrusted_content,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


def set_decision_status(db: Session, decision_id: int, status: str) -> DecisionLog | None:
    """Returns None if decision_id doesn't exist, rather than raising —
    the MCP tool wrapper decides how to surface that, this module just
    reports what happened."""
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")
    decision = db.query(DecisionLog).filter_by(id=decision_id).one_or_none()
    if decision is None:
        return None
    decision.status = status
    db.commit()
    db.refresh(decision)
    return decision


def get_decisions(
    db: Session,
    broker: str | None = None,
    symbol: str | None = None,
    include_quarantined: bool = False,
    limit: int | None = None,
) -> list[DecisionLog]:
    """Newest-first — unlike get_thesis_history, the most useful view of
    calls made is usually "what did I most recently commit to," not the
    origin story.

    Task 35: by default, omits a row that touched untrusted content and
    hasn't been human-reviewed yet — same quarantine rule as
    get_thesis_history, see that function's docstring.

    Task 36: limit, when given, caps to the N most recent rows — used by the
    digest's agent section to bound how much decision-log context it embeds,
    without needing a separate get_recent_decisions function (broker/symbol
    already default to "no filter," so this is already the aggregate query)."""
    query = db.query(DecisionLog)
    if broker is not None:
        query = query.filter_by(broker=broker)
    if symbol is not None:
        query = query.filter_by(symbol=symbol)
    if not include_quarantined:
        query = query.filter(
            not_(and_(DecisionLog.touched_untrusted_content.is_(True), DecisionLog.reviewed.is_(False)))
        )
    query = query.order_by(DecisionLog.created_at.desc(), DecisionLog.id.desc())
    if limit is not None:
        query = query.limit(limit)
    return query.all()
