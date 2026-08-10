from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("broker", "symbol", name="uq_holding_broker_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    symbol: Mapped[str] = mapped_column()
    exchange: Mapped[str] = mapped_column()
    isin: Mapped[str | None] = mapped_column(default=None)

    quantity: Mapped[float] = mapped_column()
    avg_cost: Mapped[float] = mapped_column()
    ltp: Mapped[float] = mapped_column()
    close_price: Mapped[float | None] = mapped_column(default=None)

    currency: Mapped[str] = mapped_column()
    market_value: Mapped[float] = mapped_column()
    market_value_inr: Mapped[float] = mapped_column()
    pnl_abs: Mapped[float] = mapped_column()
    pnl_pct: Mapped[float] = mapped_column()

    sector: Mapped[str | None] = mapped_column(default=None)
    asset_class: Mapped[str] = mapped_column()
    source: Mapped[str] = mapped_column()
    last_synced_at: Mapped[datetime | None] = mapped_column(default=None)

    # Task 32 — free-text "why I own this," independent of Threshold.notes
    # (which is scoped to a stop-loss/target and disappears if that
    # threshold is ever cleared). Zero ceremony by design: no structured
    # fields, just a place to jot a reason for task 29's panel to read.
    notes: Mapped[str | None] = mapped_column(default=None)
