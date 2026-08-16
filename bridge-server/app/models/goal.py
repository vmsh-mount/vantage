from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class Goal(Base):
    """Compass (docs/compass-prd.md §6.1): a single number checked against
    a single target, over a period. One table for every scalar metric
    type (price_return_pct, dividend_coverage, dividend_amount in v1 —
    see app/goals.py's dispatcher) — `comparison` supports both "gte" and
    "lte" even though every v1 metric type happens to be a floor, so a
    future ceiling-style goal is a config value, not a schema change."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    metric_type: Mapped[str] = mapped_column()
    scope_type: Mapped[str] = mapped_column(default="portfolio")  # "portfolio" | "sector" | "holding"
    scope_value: Mapped[str | None] = mapped_column(default=None)  # sector name, or "broker:symbol"
    comparison: Mapped[str] = mapped_column(default="gte")  # "gte" | "lte"
    target_value: Mapped[float] = mapped_column()
    period: Mapped[str] = mapped_column(default="monthly")
    # "monthly" | "quarterly" | "yearly" | "trailing_n_months"
    period_n: Mapped[int | None] = mapped_column(default=None)  # N, only for trailing_n_months
    # Why you set this particular goal, in your own words — optional, free
    # text, never inferred or auto-generated. Same field/purpose as
    # AllocationTarget.rationale and Milestone.rationale.
    rationale: Mapped[str | None] = mapped_column(nullable=True, default=None)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
