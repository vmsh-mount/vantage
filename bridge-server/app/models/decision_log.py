from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class DecisionLog(Base):
    """Task 34: a concrete, checkable call captured at the moment it's made
    (headline + reference_price + horizon + success_criterion), so a later
    on-demand job can grade it against reality. Grades **call quality** —
    was the prediction correct — never user outcome; Vantage can't observe
    what you actually did at the broker (see
    docs/tasks/34-decision-log-grading.md's Scope for the full reasoning).
    `status` is user-set only (never inferred from conversation); `outcome`
    is grading-job-set only (never inferred from `status`) — the two are
    deliberately independent columns."""

    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    symbol: Mapped[str] = mapped_column()
    thesis_id: Mapped[int | None] = mapped_column(ForeignKey("theses.id"), default=None)
    headline: Mapped[str] = mapped_column()  # human-readable call, e.g. "consider trimming"
    reference_price: Mapped[float] = mapped_column()  # price at the moment of the call
    horizon_days: Mapped[int] = mapped_column()
    # Small closed vocabulary, not free text — grade_pending_decisions has to
    # mechanically evaluate this later.
    success_criterion_kind: Mapped[str] = mapped_column()  # price_above | price_below | pct_change_above | pct_change_below
    success_criterion_value: Mapped[float] = mapped_column()
    status: Mapped[str] = mapped_column(default="logged")  # logged | accepted | dismissed — user-set only
    outcome: Mapped[str | None] = mapped_column(default=None)  # met | not_met | inconclusive — grading-job-set only
    graded_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    # Task 35 — memory-poisoning defenses. See models/thesis.py's own
    # comment on this same trio of columns for the full reasoning
    # (run_session_id's real meaning, why reviewed only ever flips via
    # explicit human action).
    run_session_id: Mapped[str] = mapped_column(default="")
    touched_untrusted_content: Mapped[bool] = mapped_column(default=False)
    reviewed: Mapped[bool] = mapped_column(default=False)
