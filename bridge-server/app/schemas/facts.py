from pydantic import BaseModel


class VolatilityStopSuggestion(BaseModel):
    symbol: str
    isin: str | None
    volatility_pct: float
    suggested_stop_loss_pct: float
    current_stop_loss_pct: float | None
    reasoning: str
    data_source: str
    ind_key: str
    as_of: str


class VolatilityStopsOut(BaseModel):
    suggestions: list[VolatilityStopSuggestion]


class BenchmarkSuggestion(BaseModel):
    symbol: str
    isin: str
    buy_date: str
    window_start: str
    window_capped_by_ohlc_history: bool
    holding_return_pct: float
    nifty_return_pct: float
    fd_equivalent_return_pct: float
    underperformed_both: bool
    reasoning: str
    data_source: str
    as_of: str


class BenchmarkOut(BaseModel):
    suggestions: list[BenchmarkSuggestion]
