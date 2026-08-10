from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class ApiCallLog(Base):
    __tablename__ = "api_call_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    endpoint: Mapped[str] = mapped_column()
    status_code: Mapped[int] = mapped_column()
    called_at: Mapped[datetime] = mapped_column(default=utcnow)
