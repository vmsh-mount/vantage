import httpx

from app.config import settings
from app.integrations.base import NormalizedHolding
from app.integrations.sample_data import INDMONEY_HOLDINGS

# Verified 2026-07-22 against api-docs.indstocks.com/portfolio_funds/ once real
# credentials existed — same "wrong assumed auth scheme" mistake task 3 caught
# for PaytmMoney: this originally sent `Authorization: Bearer {token}`, but
# INDstocks expects the raw token with no "Bearer " prefix. Field names
# (trading_symbol, exchange_segment, isin, quantity, average_price,
# last_traded_price, close_price, market_value, pnl_absolute, pnl_percent) and
# the {"data": [...]} envelope already matched the original best-effort guess.
BASE_URL = "https://api.indstocks.com"
HOLDINGS_PATH = "/portfolio/holdings"


def _first(row: dict, *candidates: str, default=None):
    for key in candidates:
        if key in row and row[key] is not None:
            return row[key]
    return default


def _parse_holding(row: dict) -> NormalizedHolding:
    quantity = float(_first(row, "quantity"))
    avg_cost = float(_first(row, "average_price"))
    ltp = float(_first(row, "last_traded_price"))
    close_price_raw = _first(row, "close_price", "prev_close", "previous_close")
    market_value = float(_first(row, "market_value", default=quantity * ltp))
    pnl_abs = float(_first(row, "pnl", "pnl_absolute", default=market_value - quantity * avg_cost))
    pnl_pct = float(_first(row, "pnl_percent", default=(ltp - avg_cost) / avg_cost * 100 if avg_cost else 0))

    return NormalizedHolding(
        broker="indmoney",
        symbol=_first(row, "trading_symbol", "symbol"),
        exchange=_first(row, "exchange_segment", "exchange", default="NSE"),
        isin=_first(row, "isin"),
        quantity=quantity,
        avg_cost=avg_cost,
        ltp=ltp,
        close_price=float(close_price_raw) if close_price_raw is not None else None,
        currency="INR",
        market_value=market_value,
        pnl_abs=pnl_abs,
        pnl_pct=pnl_pct,
        sector=_first(row, "sector"),
        asset_class="india_equity",
    )


class IndmoneyClient:
    def fetch_holdings(self) -> list[NormalizedHolding]:
        if settings.indmoney_mode == "mock":
            return list(INDMONEY_HOLDINGS)

        response = httpx.get(
            f"{BASE_URL}{HOLDINGS_PATH}",
            headers={"Authorization": settings.indmoney_access_token},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            rows = payload.get("data", payload.get("holdings", []))
        elif isinstance(payload, list):
            rows = payload
        else:
            raise ValueError(f"Unrecognized INDmoney holdings response shape: {type(payload)}")

        return [_parse_holding(row) for row in rows]
