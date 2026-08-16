from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GoalIn(BaseModel):
    name: str
    metric_type: str
    target_value: float
    scope_type: str = "portfolio"
    scope_value: str | None = None
    comparison: str = "gte"
    period: str = "monthly"
    period_n: int | None = None
    rationale: str | None = None


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    metric_type: str
    scope_type: str
    scope_value: str | None
    comparison: str
    target_value: float
    period: str
    period_n: int | None
    rationale: str | None
    active: bool
    created_at: datetime


class GoalsListOut(BaseModel):
    goals: list[GoalOut]
