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
