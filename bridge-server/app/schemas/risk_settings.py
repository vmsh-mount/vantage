from pydantic import BaseModel, ConfigDict, Field


class RiskSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    concentration_stock_pct: float
    concentration_sector_pct: float
    target_india_pct: float | None
    target_us_pct: float | None


class RiskSettingsIn(BaseModel):
    concentration_stock_pct: float | None = Field(default=None, gt=0, le=100)
    concentration_sector_pct: float | None = Field(default=None, gt=0, le=100)
    target_india_pct: float | None = Field(default=None, ge=0, le=100)
    target_us_pct: float | None = Field(default=None, ge=0, le=100)
