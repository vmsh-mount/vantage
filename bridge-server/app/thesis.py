"""Task 33 (planning-phase2.md §7.1): append-only, versioned investment-thesis
records per holding. Deliberately thin — no validation beyond what the
column types already enforce (conviction's 1-5 range is advisory in the
tool docstring, not enforced here, since a slightly-out-of-range value is
harmless and this table has no consumer yet that assumes the range holds).
Kept separate from app/vantage_mcp.py so the persistence logic is testable
without going through an MCP tool call, matching the app/facts/*.py and
app/tax/suggestions.py split elsewhere in this project.

Task 35 added run_session_id/touched_untrusted_content/reviewed — see
models/thesis.py's own comment on those columns and app/run_context.py's
docstring for the full provenance/quarantine story."""

from sqlalchemy import and_, not_
from sqlalchemy.orm import Session

from app.models import Thesis


def add_thesis_entry(
    db: Session,
    broker: str,
    symbol: str,
    text: str,
    conviction: int | None = None,
    run_session_id: str = "",
    touched_untrusted_content: bool = False,
) -> Thesis:
    """Insert-only — there is no update/delete path for this table anywhere
    in this project. A second entry for the same (broker, symbol) is a new
    row, never an overwrite of the first."""
    entry = Thesis(
        broker=broker,
        symbol=symbol,
        text=text,
        conviction=conviction,
        run_session_id=run_session_id,
        touched_untrusted_content=touched_untrusted_content,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_thesis_history(
    db: Session, broker: str, symbol: str, include_quarantined: bool = False
) -> list[Thesis]:
    """Oldest-first, so the agent can see the view evolving rather than only
    the latest snapshot — the "current" thesis is just the last item in this
    list, not a separately-tracked pointer.

    Task 35: by default, omits a row that touched untrusted content and
    hasn't been human-reviewed yet — a poisoned write must not shape a
    future run's context just because it was never rejected. Pass
    include_quarantined=True for explicit review (app/routers/quarantine.py),
    never for routine reads."""
    query = db.query(Thesis).filter_by(broker=broker, symbol=symbol)
    if not include_quarantined:
        query = query.filter(not_(and_(Thesis.touched_untrusted_content.is_(True), Thesis.reviewed.is_(False))))
    return query.order_by(Thesis.created_at.asc(), Thesis.id.asc()).all()


def get_recent_theses(db: Session, limit: int = 20) -> list[Thesis]:
    """Newest-first, across every holding, always quarantine-filtered (task
    35) — unlike get_thesis_history, no broker/symbol scoping, since task
    36's digest agent section wants recent context across the whole
    portfolio, not one holding at a time."""
    return (
        db.query(Thesis)
        .filter(not_(and_(Thesis.touched_untrusted_content.is_(True), Thesis.reviewed.is_(False))))
        .order_by(Thesis.created_at.desc(), Thesis.id.desc())
        .limit(limit)
        .all()
    )
