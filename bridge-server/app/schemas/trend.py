from datetime import datetime

from pydantic import BaseModel


class TrendPoint(BaseModel):
    captured_at: datetime
    total_net_worth_inr: float


class TrendOut(BaseModel):
    points: list[TrendPoint]
