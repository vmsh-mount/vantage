from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Holding, Threshold
from app.schemas.alerts import AlertItem, AlertsOut
from app.trajectory import compute_today_move, compute_trajectory

router = APIRouter()


@router.get("/api/alerts", response_model=AlertsOut)
def get_alerts(db: Session = Depends(get_db)) -> AlertsOut:
    holdings = db.query(Holding).all()
    thresholds = {(t.broker, t.symbol): t for t in db.query(Threshold).all()}

    alerts: list[AlertItem] = []

    # Stop-loss breaches apply to any holding, including manual — P&L vs.
    # avg_cost doesn't need a live feed to evaluate.
    for h in holdings:
        threshold = thresholds.get((h.broker, h.symbol))
        if threshold is not None and threshold.stop_loss_pct is not None and h.pnl_pct <= threshold.stop_loss_pct:
            alerts.append(
                AlertItem(
                    kind="stop_loss",
                    broker=h.broker,
                    symbol=h.symbol,
                    severity="loss",
                    title=f"{h.symbol} hit stop-loss ({h.pnl_pct:.1f}%, threshold {threshold.stop_loss_pct:.0f}%)",
                )
            )

    # Big-mover alerts reuse Trajectory's unusual-move z-score (task 7) rather
    # than a separate flat-% rule — see planning.md decision #10. Manual
    # holdings are skipped entirely: no live price feed for a move to be
    # "unusual" about (decision #9).
    for h in holdings:
        if h.source == "manual":
            continue
        _, move_pct, _ = compute_today_move(db, h)
        trajectory = compute_trajectory(db, h, move_pct)
        if trajectory.flag_kind == "unusual" and move_pct is not None:
            direction = "up" if move_pct >= 0 else "down"
            alerts.append(
                AlertItem(
                    kind="mover",
                    broker=h.broker,
                    symbol=h.symbol,
                    severity="gain" if move_pct >= 0 else "loss",
                    title=f"{h.symbol} {direction} {abs(move_pct):.1f}% today — {trajectory.flag_text}",
                )
            )

    return AlertsOut(alerts=alerts)
