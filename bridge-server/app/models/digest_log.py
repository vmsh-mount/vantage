from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class DigestLog(Base):
    """One row per daily-digest run attempt (task 27) — the durable half of
    the dead-man's-switch: even if every email (main and fallback) fails to
    send, this row still exists for the next run to notice the gap."""

    __tablename__ = "digest_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_at: Mapped[datetime] = mapped_column(default=utcnow)
    status: Mapped[str] = mapped_column()  # "sent" | "fallback_sent" | "failed"
    error: Mapped[str | None] = mapped_column(default=None)
