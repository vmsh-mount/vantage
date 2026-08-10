"""Volatility-scaled stop-loss suggestions (task 25). Uses bridge-server's
own INDmoney MCP client (task 24) to fetch real OHLC — no fabricated
history, no backfill. Every result carries where it came from (invariant
#5, planning-phase2.md §2.5)."""

import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.integrations.indmoney_mcp import call_tool
from app.models import Holding, Threshold

VOLATILITY_MULTIPLIER = 2.5
# A degenerately tight stop isn't useful even on an ultra-stable stock; a
# looser-than-this suggestion arguably isn't a stop-loss anymore.
STOP_LOSS_FLOOR_PCT = -5.0
STOP_LOSS_CEILING_PCT = -25.0
TRAILING_WINDOW_DAYS = 60
MIN_RETURNS_FOR_ESTIMATE = 5  # below this a stdev isn't a trustworthy estimate


async def _resolve_ind_key(symbol: str) -> str | None:
    # Name-based fuzzy match — there is no ISIN-lookup tool on the INDmoney
    # MCP surface (confirmed live, task 25 doc). First match taken as
    # best-effort; a documented limitation, not assumed precise.
    matches = await call_tool("lookup_ind_keys", {"names": [symbol], "filter_type": "IN_STOCKS"})
    if not matches:
        return None
    return matches[0]["ind_key"]


def _daily_returns_pct(candles: list[dict]) -> list[float]:
    closes = [c["close"] for c in candles]
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1] * 100
        for i in range(1, len(closes))
        if closes[i - 1]
    ]


def _trailing_window(candles: list[dict], days: int) -> list[dict]:
    # The OHLC tool has no 30/60/90-day lookback option (fixed enum:
    # 1d/7d/14d/1y — confirmed live, task 25 doc) — fetch the 1y ceiling
    # and trim client-side rather than over-fetching being wasted.
    if not candles:
        return []
    cutoff = datetime.fromisoformat(candles[-1]["datetime_ist"]) - timedelta(days=days)
    return [c for c in candles if datetime.fromisoformat(c["datetime_ist"]) >= cutoff]


async def compute_volatility_stop(holding: Holding, current_threshold: Threshold | None) -> dict | None:
    ind_key = await _resolve_ind_key(holding.symbol)
    if ind_key is None:
        return None

    ohlc = await call_tool("get_indian_stocks_ohlc", {"ind_key": ind_key, "interval": "1day", "lookback": "1y"})
    candles = ohlc.get("candles", [])
    window = _trailing_window(candles, TRAILING_WINDOW_DAYS)
    returns = _daily_returns_pct(window)
    if len(returns) < MIN_RETURNS_FOR_ESTIMATE:
        return None

    volatility_pct = statistics.pstdev(returns)
    if volatility_pct <= 0:
        return None
    suggested = -(VOLATILITY_MULTIPLIER * volatility_pct)
    suggested = max(STOP_LOSS_CEILING_PCT, min(STOP_LOSS_FLOOR_PCT, suggested))

    return {
        "symbol": holding.symbol,
        "isin": holding.isin,
        "volatility_pct": round(volatility_pct, 2),
        "suggested_stop_loss_pct": round(suggested, 2),
        "current_stop_loss_pct": current_threshold.stop_loss_pct if current_threshold else None,
        "reasoning": (
            f"{holding.symbol} swings ~{volatility_pct:.1f}%/day (trailing {len(window)} sessions) — "
            f"a {suggested:.1f}% stop ≈ {abs(suggested) / volatility_pct:.1f}× that typical daily move, "
            "tight enough to protect capital, loose enough to survive normal noise."
        ),
        "data_source": "indmoney_mcp:get_indian_stocks_ohlc",
        "ind_key": ind_key,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


async def get_volatility_stops(db: Session) -> list[dict]:
    holdings = db.query(Holding).filter(Holding.source == "api").all()
    thresholds = {(t.broker, t.symbol): t for t in db.query(Threshold).all()}

    results = []
    for h in holdings:
        threshold = thresholds.get((h.broker, h.symbol))
        result = await compute_volatility_stop(h, threshold)
        if result is not None:
            results.append(result)
    return results
