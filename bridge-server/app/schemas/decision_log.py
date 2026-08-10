from datetime import datetime

from pydantic import BaseModel


class DecisionLogOut(BaseModel):
    id: int
    broker: str
    symbol: str
    thesis_id: int | None
    headline: str
    reference_price: float
    horizon_days: int
    success_criterion_kind: str
    success_criterion_value: float
    status: str
    outcome: str | None
    graded_at: datetime | None
    created_at: datetime


class GradeDecisionsOut(BaseModel):
    graded: list[DecisionLogOut]
