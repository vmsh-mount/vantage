from datetime import date, datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class HarvestingPosition(Base):
    """One currently-held row from PaytmMoney's Tax Gain/Loss Harvesting Report —
    unrealized P&L per holding, no buy date (see Trade for that). Replace-on-import
    per (broker, as_on_date): see task 21."""

    __tablename__ = "harvesting_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    as_on_date: Mapped[date] = mapped_column()
    # "loss_offset_short_term" | "loss_offset_long_term" | "gain_opportunity_long_term"
    kind: Mapped[str] = mapped_column()
    scrip_name: Mapped[str] = mapped_column()
    isin: Mapped[str] = mapped_column()
    quantity: Mapped[float] = mapped_column()
    buy_avg: Mapped[float] = mapped_column()
    buy_value: Mapped[float] = mapped_column()
    closing_price: Mapped[float] = mapped_column()
    present_value: Mapped[float] = mapped_column()
    unrealized_pnl: Mapped[float] = mapped_column()
    imported_at: Mapped[datetime] = mapped_column(default=utcnow)


class HarvestingSummary(Base):
    """The top-line figures from one Harvesting Report import — one row per
    (broker, as_on_date) snapshot, replaced on re-import."""

    __tablename__ = "harvesting_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    as_on_date: Mapped[date] = mapped_column()
    financial_year: Mapped[str] = mapped_column()
    stcg_realized: Mapped[float] = mapped_column()
    stcl_unrealized: Mapped[float] = mapped_column()
    ltcg_realized: Mapped[float] = mapped_column()
    ltcl_unrealized: Mapped[float] = mapped_column()
    st_harvest_opportunity: Mapped[float] = mapped_column()
    lt_harvest_opportunity: Mapped[float] = mapped_column()
    lt_gain_harvest_opportunity: Mapped[float] = mapped_column()
    imported_at: Mapped[datetime] = mapped_column(default=utcnow)
