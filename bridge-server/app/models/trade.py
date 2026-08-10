from datetime import date, datetime

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class Trade(Base):
    __tablename__ = "trades"
    # Trade Number was '0' on every real Trade Book row (not usable for dedup);
    # Order Number was unique per execution — see task 21.
    __table_args__ = (UniqueConstraint("broker", "order_number", name="uq_trade_broker_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    trade_date: Mapped[date] = mapped_column()
    # PaytmMoney's internal numeric security code (e.g. "532898"), not a ticker —
    # joins to Holding/Threshold via isin, not symbol.
    script_code: Mapped[str] = mapped_column()
    isin: Mapped[str] = mapped_column()
    exchange: Mapped[str] = mapped_column()
    product_type: Mapped[str] = mapped_column()
    txn_type: Mapped[str] = mapped_column()  # "BUY" | "SELL"
    quantity: Mapped[float] = mapped_column()
    price: Mapped[float] = mapped_column()
    brokerage: Mapped[float] = mapped_column()
    ett: Mapped[float] = mapped_column()
    gst: Mapped[float] = mapped_column()
    stt: Mapped[float] = mapped_column()
    sebi: Mapped[float] = mapped_column()
    stamp_duty: Mapped[float] = mapped_column()
    order_number: Mapped[str] = mapped_column()
    trade_number: Mapped[str] = mapped_column()
    trade_time: Mapped[str | None] = mapped_column(default=None)
    imported_at: Mapped[datetime] = mapped_column(default=utcnow)
