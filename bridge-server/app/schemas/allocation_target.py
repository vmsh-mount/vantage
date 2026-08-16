from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AllocationTargetIn(BaseModel):
    dimension: str
    bucket: str
    target_pct: float = Field(gt=0, le=100)
    tolerance_pct: float = Field(default=5.0, ge=0, le=100)
    rationale: str | None = None


class AllocationTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dimension: str
    bucket: str
    target_pct: float
    tolerance_pct: float
    rationale: str | None
    active: bool
    created_at: datetime


class AllocationTargetsListOut(BaseModel):
    targets: list[AllocationTargetOut]


class AllocationProgressItem(BaseModel):
    id: int
    dimension: str
    bucket: str
    target_pct: float
    tolerance_pct: float
    rationale: str | None
    actual_pct: float
    actual_value_inr: float
    status: str  # "on_target" | "underweight" | "overweight"
    gap_pct: float
    # Which comma-separated part(s) of `bucket` don't match any real
    # sector/asset-class/region among current holdings — empty when every
    # part matches. See compute_allocation_progress's own docstring for
    # why this exists (a typo and a genuine zero-holding gap used to be
    # indistinguishable).
    unmatched_bucket_names: list[str]


class AllocationProgressOut(BaseModel):
    dimension: str
    progress: list[AllocationProgressItem]


class DimensionBreakdownItem(BaseModel):
    bucket: str
    actual_pct: float
    actual_value_inr: float


class DimensionBreakdownOut(BaseModel):
    dimension: str
    breakdown: list[DimensionBreakdownItem]
