from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class AllocationTarget(Base):
    """Compass (docs/compass-prd.md §6.2): a target composition across
    buckets within a dimension (e.g. dimension="sector", bucket=
    "Technology", target_pct=20) — the real fix for "spread across
    sectors": a bucket with real 0% actual against a real target is a
    named, specific gap, not just "one short of a count."

    Supported dimensions in v1: "sector", "asset_class", "region" — all
    computed from Holding data already local to bridge-server (reusing
    app/breakdowns.py, the same grouping the dashboard's own breakdown
    charts use). "market_cap" is a real, named gap in what's buildable
    right now: INDmoney's own market-data lookup has it
    (get_indian_stocks_details returns market_cap per stock), but Holding
    doesn't store it locally, so computing that dimension would mean a
    live per-holding INDmoney call on every progress check — the same
    cost profile as facts/volatility.py's real rate-limit exposure, not
    a free local aggregation like the other three. Deliberately not
    wired up in this pass rather than silently shipping a slow/
    rate-limited dimension without calling it out; a real, separate
    follow-up (a cached per-holding market-cap lookup, refreshed on the
    sync tick, mirroring how `sector` itself is already synced) is the
    right way to add it later."""

    __tablename__ = "allocation_targets"
    __table_args__ = (UniqueConstraint("dimension", "bucket", name="uq_allocation_target_dimension_bucket"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dimension: Mapped[str] = mapped_column()  # "sector" | "asset_class" | "region"
    bucket: Mapped[str] = mapped_column()
    target_pct: Mapped[float] = mapped_column()
    tolerance_pct: Mapped[float] = mapped_column(default=5.0)
    # Why this particular target, in the user's own words (e.g. "avoid
    # repeating the 2025 IT-sector concentration") — optional, free text,
    # never inferred or auto-generated. Shown alongside the bucket's real
    # progress so the number and the reasoning behind it stay together.
    rationale: Mapped[str | None] = mapped_column(nullable=True, default=None)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
