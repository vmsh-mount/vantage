from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RiskSettings(Base):
    __tablename__ = "risk_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    concentration_stock_pct: Mapped[float] = mapped_column(default=15)
    concentration_sector_pct: Mapped[float] = mapped_column(default=30)
    target_india_pct: Mapped[float | None] = mapped_column(default=None)
    target_us_pct: Mapped[float | None] = mapped_column(default=None)
