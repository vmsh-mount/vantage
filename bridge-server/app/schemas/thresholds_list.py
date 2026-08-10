from pydantic import BaseModel


class ThresholdListItem(BaseModel):
    broker: str
    symbol: str
    stop_loss_pct: float | None
    target_pct: float | None
    notes: str | None


class ThresholdsListOut(BaseModel):
    thresholds: list[ThresholdListItem]
