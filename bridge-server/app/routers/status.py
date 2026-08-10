from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import ApiCallLog, DigestLog
from app.scheduler import run_sync_pipeline
from app.schemas.status import BrokerStatus, BrokerSyncResult, DigestStatus, RefreshOut, StatusOut

router = APIRouter()

BROKERS = ["paytmmoney", "indmoney"]
REGENERATE_HINT = {
    "paytmmoney": "regenerate via `make login` (scripts/paytmmoney_login.py)",
    "indmoney": "regenerate at indstocks.com/app/api-trading",
}


def _mode_for(broker: str) -> str:
    return settings.paytmmoney_mode if broker == "paytmmoney" else settings.indmoney_mode


def _broker_status(db: Session, broker: str) -> BrokerStatus:
    mode = _mode_for(broker)
    last_call = (
        db.query(ApiCallLog).filter_by(broker=broker).order_by(ApiCallLog.called_at.desc()).first()
    )
    last_success = (
        db.query(ApiCallLog)
        .filter_by(broker=broker, status_code=200)
        .order_by(ApiCallLog.called_at.desc())
        .first()
    )

    warning = None
    healthy = True
    if last_call is not None and last_call.status_code != 200:
        healthy = False
        if mode == "live" and last_call.status_code in (401, 403):
            warning = f"{broker} token expired or rejected — {REGENERATE_HINT[broker]}"
        else:
            warning = (
                f"{broker} sync failed (status {last_call.status_code}) — "
                "check bridge-server/logs/api_calls.log"
            )

    return BrokerStatus(
        broker=broker,
        mode=mode,
        last_sync_at=last_success.called_at if last_success else None,
        healthy=healthy,
        warning=warning,
    )


def _digest_status(db: Session) -> DigestStatus:
    last = db.query(DigestLog).order_by(DigestLog.run_at.desc()).first()
    if last is None:
        return DigestStatus(last_run_at=None, last_status=None, last_error=None)
    return DigestStatus(last_run_at=last.run_at, last_status=last.status, last_error=last.error)


@router.get("/api/status", response_model=StatusOut)
def get_status(db: Session = Depends(get_db)) -> StatusOut:
    return StatusOut(
        brokers=[_broker_status(db, broker) for broker in BROKERS],
        digest=_digest_status(db),
    )


# run_sync_pipeline() (scheduler.py) owns the actual concurrency guard, since
# it's the one function both this endpoint and the periodic interval tick
# call — a lock defined only here would protect manual refreshes against
# each other but do nothing about the far more likely collision: a manual
# refresh landing at the same moment the scheduler's own tick fires. A
# literal time-based cooldown ("reject if called again within 10s") would
# also reject the second of two legitimate back-to-back calls, directly
# contradicting this task's own acceptance criteria ("called twice in a row
# both complete") — the shared lock satisfies both instead.
@router.post("/api/refresh", response_model=RefreshOut)
def refresh() -> RefreshOut:
    results = run_sync_pipeline()
    if results is None:
        raise HTTPException(
            status_code=429,
            detail="A sync is already in progress (manual refresh or the scheduled tick) — try again shortly.",
        )
    return RefreshOut(results={broker: BrokerSyncResult(**r) for broker, r in results.items()})
