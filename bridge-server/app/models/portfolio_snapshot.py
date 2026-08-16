from datetime import datetime

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(default=utcnow)
    total_net_worth_inr: Mapped[float] = mapped_column()
    breakdown_json: Mapped[dict] = mapped_column(JSON)
    # Added for Milestone's pnl_pct metric type (docs/compass-prd.md §6.3 —
    # e.g. a break-even-by-date milestone). Nullable: rows written before
    # this existed have no per-holding cost-basis history to backfill it
    # from, so old snapshots genuinely have no value here — the pace
    # calculator treats those the same as "not enough data yet," never a
    # fabricated 0.
    total_pnl_pct: Mapped[float | None] = mapped_column(nullable=True, default=None)
