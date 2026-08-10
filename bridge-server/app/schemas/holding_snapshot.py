from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HoldingSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    captured_at: datetime
    broker: str
    symbol: str
    market_value_inr: float
    ltp: float
    pnl_pct: float
