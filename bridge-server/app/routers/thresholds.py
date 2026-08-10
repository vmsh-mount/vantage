from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Holding, Threshold
from app.schemas.threshold import ThresholdIn, ThresholdOut
from app.schemas.thresholds_list import ThresholdListItem, ThresholdsListOut

router = APIRouter()


@router.get("/api/thresholds", response_model=ThresholdsListOut)
def list_thresholds(db: Session = Depends(get_db)) -> ThresholdsListOut:
    holdings = db.query(Holding).all()
    thresholds = {(t.broker, t.symbol): t for t in db.query(Threshold).all()}

    items = []
    for h in holdings:
        t = thresholds.get((h.broker, h.symbol))
        items.append(
            ThresholdListItem(
                broker=h.broker,
                symbol=h.symbol,
                stop_loss_pct=t.stop_loss_pct if t else None,
                target_pct=t.target_pct if t else None,
                notes=t.notes if t else None,
            )
        )
    return ThresholdsListOut(thresholds=items)


def _upsert_threshold(payload: ThresholdIn, db: Session) -> Threshold:
    existing = db.query(Threshold).filter_by(broker=payload.broker, symbol=payload.symbol).one_or_none()
    if existing is None:
        existing = Threshold(broker=payload.broker, symbol=payload.symbol)
        db.add(existing)
    # Only overwrite fields actually present in the payload — same pattern as
    # settings.py's update_risk_settings in this same task. A payload that only
    # sets target_pct (e.g. adding a profit target sometime after the stop-loss
    # was already set) must not silently null out stop_loss_pct. To fully clear
    # a threshold, use DELETE, not an omitted field here.
    if payload.stop_loss_pct is not None:
        existing.stop_loss_pct = payload.stop_loss_pct
    if payload.target_pct is not None:
        existing.target_pct = payload.target_pct
    if payload.notes is not None:
        existing.notes = payload.notes
    db.commit()
    db.refresh(existing)
    return existing


@router.post("/api/thresholds", response_model=ThresholdOut)
def create_threshold(payload: ThresholdIn, db: Session = Depends(get_db)) -> Threshold:
    return _upsert_threshold(payload, db)


@router.put("/api/thresholds", response_model=ThresholdOut)
def update_threshold(payload: ThresholdIn, db: Session = Depends(get_db)) -> Threshold:
    return _upsert_threshold(payload, db)


@router.delete("/api/thresholds", status_code=204)
def delete_threshold(
    broker: str = Query(...), symbol: str = Query(...), db: Session = Depends(get_db)
) -> None:
    existing = db.query(Threshold).filter_by(broker=broker, symbol=symbol).one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="No threshold set for that holding")
    db.delete(existing)
    db.commit()
