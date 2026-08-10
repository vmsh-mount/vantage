from pydantic import BaseModel


class ConcentrationFlag(BaseModel):
    kind: str  # "stock" | "sector"
    label: str
    pct: float
    limit_pct: float


class RegionSplit(BaseModel):
    india_pct: float
    us_pct: float
    target_india_pct: float | None
    target_us_pct: float | None
    drift_pct: float | None  # india_pct - target_india_pct, signed; null with no target set


class RiskOut(BaseModel):
    concentration_flags: list[ConcentrationFlag]
    region_split: RegionSplit
