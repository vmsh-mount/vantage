from pydantic import BaseModel, ConfigDict, Field


class ThresholdOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker: str
    symbol: str
    stop_loss_pct: float | None
    target_pct: float | None
    notes: str | None


class ThresholdIn(BaseModel):
    broker: str
    symbol: str
    # Sign convention (architecture.md's Threshold row): stop_loss_pct negative,
    # target_pct positive. Validated here rather than left to guess wrong later —
    # task 2 flagged this as a likely input mistake worth rejecting outright.
    stop_loss_pct: float | None = Field(default=None, lt=0)
    target_pct: float | None = Field(default=None, gt=0)
    notes: str | None = None
