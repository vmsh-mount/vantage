from typing import Protocol

from pydantic import BaseModel


class NormalizedHolding(BaseModel):
    broker: str
    symbol: str
    exchange: str
    isin: str | None = None

    quantity: float
    avg_cost: float
    ltp: float
    close_price: float | None = None

    currency: str
    market_value: float
    pnl_abs: float
    pnl_pct: float

    sector: str | None = None
    asset_class: str
    source: str = "api"


class BrokerClient(Protocol):
    def fetch_holdings(self) -> list[NormalizedHolding]: ...
