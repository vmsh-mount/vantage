from pydantic import BaseModel, Field

from app.schemas.holding import HoldingOut


class ManualHoldingIn(BaseModel):
    symbol: str
    quantity: float = Field(gt=0)
    avg_cost: float = Field(gt=0)
    sector: str | None = None
    exchange: str = "NASDAQ"
    # On create: omit to price at avg_cost (fresh baseline, nothing to preserve).
    # On edit: omit to keep the holding's current price unchanged — only
    # provide this when you actually want to reprice it.
    ltp: float | None = None


class CsvImportIn(BaseModel):
    csv: str


class CsvImportSkippedRow(BaseModel):
    line_number: int
    raw: str
    reason: str


class CsvImportOut(BaseModel):
    imported: list[HoldingOut]
    skipped: list[CsvImportSkippedRow]
