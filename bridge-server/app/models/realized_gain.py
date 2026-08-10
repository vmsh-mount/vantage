from datetime import date, datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class RealizedGain(Base):
    """One already-lot-matched row from PaytmMoney's own Tax P&L Statement
    (Equity sheet) — PaytmMoney does the FIFO matching, we just store it.
    Replace-on-import per (broker, financial_year): see task 21."""

    __tablename__ = "realized_gains"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    financial_year: Mapped[str] = mapped_column()  # e.g. "FY 2025-26"
    term: Mapped[str] = mapped_column()  # "intraday" | "short_term" | "long_term"
    quarter: Mapped[str | None] = mapped_column(default=None)
    scrip_name: Mapped[str] = mapped_column()
    isin: Mapped[str] = mapped_column()
    quantity: Mapped[float] = mapped_column()
    buy_date: Mapped[date] = mapped_column()
    buy_price: Mapped[float] = mapped_column()
    buy_value: Mapped[float] = mapped_column()
    sell_date: Mapped[date] = mapped_column()
    sell_price: Mapped[float] = mapped_column()
    sell_value: Mapped[float] = mapped_column()
    net_realized_pnl: Mapped[float] = mapped_column()
    brokerage: Mapped[float] = mapped_column()
    service_tax: Mapped[float] = mapped_column()
    stt: Mapped[float] = mapped_column()
    ett: Mapped[float] = mapped_column()
    sebi_tax: Mapped[float] = mapped_column()
    stamp_duty: Mapped[float] = mapped_column()
    total_charges: Mapped[float] = mapped_column()
    imported_at: Mapped[datetime] = mapped_column(default=utcnow)
