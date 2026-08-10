from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import utcnow


class Thesis(Base):
    """Task 33: an append-only, versioned investment-thesis record per
    holding. No UPDATE/DELETE path exists anywhere in this project for this
    table — the "current" thesis for a (broker, symbol) is just the latest
    row, a query rather than a separate mutable pointer, so there's no risk
    of a pointer disagreeing with the history it's supposed to summarize.
    Coexists with (does not replace) task 32's Holding.notes — see
    docs/tasks/33-thesis-conviction.md's Scope section for why these are two
    deliberately different weights, not one being an upgrade path for the
    other."""

    __tablename__ = "theses"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column()
    symbol: Mapped[str] = mapped_column()
    text: Mapped[str] = mapped_column()
    conviction: Mapped[int | None] = mapped_column(default=None)  # 1-5, not every entry states one
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    # Task 35 — memory-poisoning defenses. run_session_id is bridge-server's
    # own generated per-WS-connection correlator (see app/run_context.py's
    # docstring for why this isn't literally Claude CLI's own --resume
    # session_id). touched_untrusted_content is set True if that same
    # connection ever called WebFetch/WebSearch before this row was
    # written. reviewed only ever flips True via an explicit human review
    # (POST /api/quarantine/{table}/{id}/review) — never automatically.
    run_session_id: Mapped[str] = mapped_column(default="")
    touched_untrusted_content: Mapped[bool] = mapped_column(default=False)
    reviewed: Mapped[bool] = mapped_column(default=False)
