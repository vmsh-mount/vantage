import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import ApiCallLog

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_PATH = LOG_DIR / "api_calls.log"

_logger = logging.getLogger("vantage.api_calls")
_logger.setLevel(logging.INFO)
_logger.propagate = False


def _ensure_handler() -> None:
    if _logger.handlers:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(handler)


def log_api_call(db: Session, broker: str, endpoint: str, status_code: int) -> None:
    """The one place an ApiCallLog row gets written. Commits immediately rather
    than leaving it for the caller's later batched commit — the audit trail's
    durability shouldn't depend on whether some unrelated later step in the
    same sync tick (e.g. writing snapshots) also succeeds. Written to the DB
    before the file mirror, so a failed commit can't leave an orphaned file
    line with no row behind it."""
    db.add(ApiCallLog(broker=broker, endpoint=endpoint, status_code=status_code))
    db.commit()
    _ensure_handler()
    _logger.info("broker=%s endpoint=%s status_code=%s", broker, endpoint, status_code)
