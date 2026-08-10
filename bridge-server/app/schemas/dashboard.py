from pydantic import BaseModel

from app.schemas.trajectory import TrajectoryOut


class BreakdownItem(BaseModel):
    label: str
    value_inr: float
    pct: float


class DashboardHolding(BaseModel):
    id: int
    broker: str
    symbol: str
    exchange: str
    isin: str | None
    quantity: float
    avg_cost: float
    ltp: float
    close_price: float | None
    currency: str
    market_value: float
    market_value_inr: float
    pnl_abs: float
    pnl_pct: float
    sector: str | None
    asset_class: str
    source: str
    notes: str | None
    pricing: str
    today_move_abs_inr: float | None
    today_move_pct: float | None
    threshold_breached: bool
    trajectory: TrajectoryOut


class DashboardOut(BaseModel):
    net_worth_inr: float
    today_move_abs_inr: float
    today_move_pct: float
    total_pnl_abs_inr: float
    total_pnl_pct: float
    breakdowns: dict[str, list[BreakdownItem]]
    holdings: list[DashboardHolding]
