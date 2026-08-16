from datetime import date, datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class Dividend(Base):
    """Compass (docs/compass-prd.md §8): manual dividend log. No broker API
    exposes dividend data in any form — confirmed live against both real
    accounts (INDmoney's MCP surface has no dividend field anywhere;
    PaytmMoney's full Trading API has no dividend/corporate-actions
    endpoint, and its one lead, funds_summary(config=True), turned out to
    be balance/limits metadata, not a transaction ledger). This table is
    the only way dividend data enters Vantage — a deliberate user action,
    not something a sync job or an agent infers.

    amount_inr only, no currency field: every dividend-eligible holding
    this project tracks is India-listed (US holdings are manual-entry,
    no-dividend-feed territory already, per Manual Holdings' own scope)."""

    __tablename__ = "dividends"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    symbol: Mapped[str] = mapped_column()
    amount_inr: Mapped[float] = mapped_column()
    payment_date: Mapped[date] = mapped_column()
    notes: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
