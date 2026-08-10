from pydantic import BaseModel


class TrajectoryOut(BaseModel):
    cold_start: bool = False
    static: bool = False
    days_available: int | None = None
    recent_days: int | None = None
    recent_return_pct: float | None = None
    thirty_day_days: int | None = None
    thirty_day_return_pct: float | None = None
    flag_kind: str | None = None
    flag_text: str | None = None
