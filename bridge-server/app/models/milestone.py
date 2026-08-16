from datetime import date, datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class Milestone(Base):
    """Compass (docs/compass-prd.md §6.3): a target reached by a date, not
    a recurring period check — net worth by a deadline is the most natural
    portfolio target there is, and needs zero new data
    (PortfolioSnapshot's own history is enough for a real pace
    projection). metric_type is "net_worth" or "pnl_pct" (e.g. a
    break-even-by-date milestone) — kept as a real column, not hardcoded,
    so each is a new calculator (app/milestones.py's SUPPORTED_METRIC_TYPES
    + _SNAPSHOT_FIELD), not a schema change. target_value has no
    positivity constraint at the DB layer since pnl_pct targets are
    legitimately 0 (break-even) or negative (e.g. "cut the loss to -5%")."""

    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    metric_type: Mapped[str] = mapped_column(default="net_worth")
    target_value: Mapped[float] = mapped_column()
    target_date: Mapped[date] = mapped_column()
    # Why you set this particular milestone, in your own words — optional,
    # free text, never inferred or auto-generated. Same field/purpose as
    # AllocationTarget.rationale; distinct from the computed pace-math
    # "Why" the progress endpoint already returns (actual/required pace,
    # trend) — that explains the *status*, this explains the *intent*.
    rationale: Mapped[str | None] = mapped_column(nullable=True, default=None)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
