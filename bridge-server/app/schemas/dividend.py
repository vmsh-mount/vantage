from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DividendIn(BaseModel):
    broker: str
    symbol: str
    amount_inr: float = Field(gt=0)
    payment_date: date
    notes: str | None = None


class DividendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker: str
    symbol: str
    amount_inr: float
    payment_date: date
    notes: str | None
    created_at: datetime


class DividendsListOut(BaseModel):
    dividends: list[DividendOut]
