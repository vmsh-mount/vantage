from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class MilestoneIn(BaseModel):
    name: str
    metric_type: str = "net_worth"
    # No Field(gt=0) here (unlike the original net_worth-only version) —
    # pnl_pct targets are legitimately 0 (break-even) or negative (e.g.
    # "cut the loss to -5%"). metric_type-conditional validation (net_worth
    # must be positive) happens in the router, same place Goal's
    # metric_type is validated.
    target_value: float
    target_date: date
    rationale: str | None = None


class MilestoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    metric_type: str
    target_value: float
    target_date: date
    rationale: str | None
    active: bool
    created_at: datetime


class MilestonesListOut(BaseModel):
    milestones: list[MilestoneOut]


class MilestoneProgressOut(BaseModel):
    id: int
    name: str
    metric_type: str
    target_value: float
    target_date: str
    rationale: str | None
    current_value: float | None
    progress_pct: float | None
    status: str  # "met" | "on_pace" | "behind" | "not_enough_data"
    actual_pace_per_day: float | None
    required_pace_per_day: float | None
    projected_date: str | None
    days_remaining: int | None
    pace_window_days: int
