from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.breakdowns import compute_breakdown_sums, compute_net_worth_inr, compute_total_pnl
from app.db import get_db
from app.models import Holding, Threshold
from app.schemas import BreakdownItem, DashboardHolding, DashboardOut
from app.trajectory import compute_today_move, compute_trajectory

router = APIRouter()


@router.get("/api/dashboard", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardOut:
    holdings = db.query(Holding).all()
    net_worth_inr = compute_net_worth_inr(holdings)
    thresholds = {(t.broker, t.symbol): t for t in db.query(Threshold).all()}

    total_move_abs = 0.0
    holding_rows = []
    for h in holdings:
        move_abs, move_pct, pricing = compute_today_move(db, h)
        if move_abs is not None:
            total_move_abs += move_abs

        threshold = thresholds.get((h.broker, h.symbol))
        breached = bool(
            threshold is not None
            and threshold.stop_loss_pct is not None
            and h.pnl_pct <= threshold.stop_loss_pct
        )

        holding_rows.append(
            DashboardHolding(
                id=h.id,
                broker=h.broker,
                symbol=h.symbol,
                exchange=h.exchange,
                isin=h.isin,
                quantity=h.quantity,
                avg_cost=h.avg_cost,
                ltp=h.ltp,
                close_price=h.close_price,
                currency=h.currency,
                market_value=h.market_value,
                market_value_inr=h.market_value_inr,
                pnl_abs=h.pnl_abs,
                pnl_pct=h.pnl_pct,
                sector=h.sector,
                asset_class=h.asset_class,
                source=h.source,
                notes=h.notes,
                pricing=pricing,
                today_move_abs_inr=move_abs,
                today_move_pct=move_pct,
                threshold_breached=breached,
                trajectory=compute_trajectory(db, h, move_pct),
            )
        )

    yesterday_net_worth_inr = net_worth_inr - total_move_abs
    today_move_pct = (total_move_abs / yesterday_net_worth_inr * 100) if yesterday_net_worth_inr else 0.0

    total_pnl_abs_inr, total_pnl_pct = compute_total_pnl(holdings)

    breakdowns = {
        key: [
            BreakdownItem(
                label=label,
                value_inr=value,
                pct=(value / net_worth_inr * 100) if net_worth_inr else 0.0,
            )
            for label, value in group.items()
        ]
        for key, group in compute_breakdown_sums(holdings).items()
    }

    return DashboardOut(
        net_worth_inr=net_worth_inr,
        today_move_abs_inr=total_move_abs,
        today_move_pct=today_move_pct,
        total_pnl_abs_inr=total_pnl_abs_inr,
        total_pnl_pct=total_pnl_pct,
        breakdowns=breakdowns,
        holdings=holding_rows,
    )
