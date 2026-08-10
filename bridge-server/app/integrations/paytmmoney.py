import httpx

from app.config import settings
from app.integrations.base import NormalizedHolding
from app.integrations.sample_data import PAYTMMONEY_HOLDINGS

BASE_URL = "https://developer.paytmmoney.com"
HOLDINGS_PATH = "/holdings/v1/get-user-holdings-data"


def _first(row: dict, *candidates: str, default=None):
    for key in candidates:
        if key in row and row[key] is not None:
            return row[key]
    return default


def _parse_holding(row: dict) -> NormalizedHolding:
    # Field names verified 2026-07-19 against a real authenticated response
    # (see docs/tasks/03-broker-integrations.md) — the real names ("cost_price",
    # "nse_symbol", "isin_code", "pc") differ from what planning.md's docs-site
    # research suggested, kept as lower-priority fallbacks in case the shape
    # varies by holding/segment type.
    quantity = float(_first(row, "quantity", "qty"))
    avg_cost = float(_first(row, "cost_price", "avg_price", "average_price", "avg_cost"))
    ltp = float(_first(row, "last_traded_price", "ltp"))
    # "pc" = previous close, confirmed against 23 real holdings: small,
    # plausible daily moves in both directions, present on every row.
    close_price_raw = _first(row, "pc", "close_price", "prev_close", "previous_close")
    market_value = float(_first(row, "market_value", "current_value", default=quantity * ltp))
    pnl_abs = float(_first(row, "pnl", "pnl_absolute", "overall_pnl", default=market_value - quantity * avg_cost))
    pnl_pct = float(_first(row, "pnl_percent", "pnl_percentage", default=(ltp - avg_cost) / avg_cost * 100 if avg_cost else 0))

    return NormalizedHolding(
        broker="paytmmoney",
        symbol=_first(row, "nse_symbol", "bse_symbol", "symbol", "trading_symbol", "tradingsymbol"),
        # PaytmMoney's own "exchange" field is the literal string "ALL" (dual-listed),
        # not a real per-holding exchange — PaytmMoney is NSE/BSE-only by construction
        # (India-only broker), and nse_symbol is used as the canonical symbol above,
        # so NSE is the correct, non-guessed value here rather than parsing "ALL".
        exchange="NSE",
        isin=_first(row, "isin_code", "isin"),
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


class PaytmMoneyClient:
    def fetch_holdings(self) -> list[NormalizedHolding]:
        if settings.paytmmoney_mode == "mock":
            return list(PAYTMMONEY_HOLDINGS)

        response = httpx.get(
            f"{BASE_URL}{HOLDINGS_PATH}",
            headers={
                "Content-Type": "application/json",
                "openapi-client-src": "sdk",
                "x-jwt-token": settings.paytmmoney_access_token,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            data = payload.get("data", {})
            # Verified real shape: {"data": {"results": [...]}}. Older guesses
            # ({"data": [...]}, {"holdings": [...]}) kept as fallbacks.
            if isinstance(data, dict):
                rows = data.get("results", [])
            elif isinstance(data, list):
                rows = data
            else:
                rows = payload.get("holdings", [])
        elif isinstance(payload, list):
            rows = payload
        else:
            raise ValueError(f"Unrecognized PaytmMoney holdings response shape: {type(payload)}")

        if rows and not isinstance(rows[0], dict):
            raise ValueError(f"Unexpected PaytmMoney holdings row shape: {rows[0]!r}")

        return [_parse_holding(row) for row in rows]
