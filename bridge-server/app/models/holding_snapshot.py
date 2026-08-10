from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class HoldingSnapshot(Base):
    __tablename__ = "holding_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(default=utcnow)
    broker: Mapped[str] = mapped_column()
    symbol: Mapped[str] = mapped_column()
    market_value_inr: Mapped[float] = mapped_column()
    ltp: Mapped[float] = mapped_column()
    pnl_pct: Mapped[float] = mapped_column()
