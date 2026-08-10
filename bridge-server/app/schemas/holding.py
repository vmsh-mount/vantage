from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HoldingNotesIn(BaseModel):
    notes: str | None


class HoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    last_synced_at: datetime | None
    notes: str | None
