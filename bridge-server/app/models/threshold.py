from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Threshold(Base):
    __tablename__ = "thresholds"
    __table_args__ = (UniqueConstraint("broker", "symbol", name="uq_threshold_broker_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    symbol: Mapped[str] = mapped_column()
    stop_loss_pct: Mapped[float | None] = mapped_column(default=None)
    target_pct: Mapped[float | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(default=None)
