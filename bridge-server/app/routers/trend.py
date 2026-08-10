from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import PortfolioSnapshot
from app.schemas.trend import TrendOut, TrendPoint

router = APIRouter()


@router.get("/api/trend", response_model=TrendOut)
def get_trend(days: int = Query(30, ge=1), db: Session = Depends(get_db)) -> TrendOut:
    window_start = datetime.now(timezone.utc) - timedelta(days=days)
    snapshots = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.captured_at >= window_start)
        .order_by(PortfolioSnapshot.captured_at)
        .all()
    )
    return TrendOut(
        points=[
            TrendPoint(captured_at=s.captured_at, total_net_worth_inr=s.total_net_worth_inr)
            for s in snapshots
        ]
    )
