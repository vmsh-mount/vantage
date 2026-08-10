from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Task 28d: WAL lets readers proceed without blocking on a writer (and
    vice versa); busy_timeout makes a second writer that arrives while
    another write is in flight retry internally for N ms instead of
    immediately raising "database is locked" — the standard SQLite recipe
    for a scheduled job and a live panel session touching the same file at
    once (docs/tasks/28d-concurrency-wal.md). Set on every new connection
    (not just once at startup) so it's self-healing if the file was ever
    created before this existed."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)


class Base(DeclarativeBase):
    pass


def _ensure_holdings_notes_column() -> None:
    """Task 32: Base.metadata.create_all only creates missing *tables* —
    Holding.notes was added after real holdings already existed in every
    checkout's local DB, so the table exists but the column doesn't, and
    create_all() silently does nothing about it. This project has no
    migration tool for one column; a self-healing ALTER TABLE on startup
    (idempotent — checked via PRAGMA table_info first) is honest about why
    it exists rather than requiring a one-off manual fix per checkout."""
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(holdings)")).fetchall()}
        if "notes" not in columns:
            conn.execute(text("ALTER TABLE holdings ADD COLUMN notes TEXT"))
            conn.commit()


def _ensure_provenance_columns() -> None:
    """Task 35: same situation as _ensure_holdings_notes_column above —
    run_session_id/touched_untrusted_content/reviewed were added to
    theses/decision_log after those tables already existed (tasks 33/34
    shipped first), so create_all() won't add them to an existing
    checkout's DB. Idempotent, self-healing, same recipe."""
    with engine.connect() as conn:
        for table, ddl in (
            ("theses", "ALTER TABLE theses ADD COLUMN {col}"),
            ("decision_log", "ALTER TABLE decision_log ADD COLUMN {col}"),
        ):
            columns = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
            if "run_session_id" not in columns:
                conn.execute(text(ddl.format(col="run_session_id VARCHAR NOT NULL DEFAULT ''")))
            if "touched_untrusted_content" not in columns:
                conn.execute(text(ddl.format(col="touched_untrusted_content BOOLEAN NOT NULL DEFAULT 0")))
            if "reviewed" not in columns:
                conn.execute(text(ddl.format(col="reviewed BOOLEAN NOT NULL DEFAULT 0")))
        conn.commit()


def init_db() -> None:
    from app.models import RiskSettings

    Base.metadata.create_all(bind=engine)
    _ensure_holdings_notes_column()
    _ensure_provenance_columns()

    with SessionLocal() as db:
        if db.query(RiskSettings).first() is None:
            db.add(RiskSettings())
            db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
