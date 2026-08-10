"""Opportunity-cost / benchmark (task 25): a holding's real return vs
NIFTY 50 vs an FD-equivalent, over the same real window — capped at
whatever OHLC history is actually reachable (the 1y ceiling confirmed
live, see task 25 doc). Only for holdings with an imported Trade Book buy
row — never fabricates a buy date (same pattern as task 22's LTCG-crossing
suggestion)."""

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.integrations.indmoney_mcp import call_tool
from app.models import Holding, Trade

# Resolved live via lookup_ind_keys(["NIFTY 50"]) during task 25 — indices
# resolve through the same call as stocks, no separate endpoint.
NIFTY_IND_KEY = "INDI00012"
# Static assumption, not fetched live — no free reliable source for a
# current FD rate. Documented, not silently baked in.
FD_ANNUAL_RATE_PCT = 7.0


def _earliest_buy_trade(db: Session, isin: str) -> Trade | None:
    return (
        db.query(Trade)
        .filter(Trade.isin == isin, Trade.txn_type == "BUY")
        .order_by(Trade.trade_date.asc())
        .first()
    )


def _nifty_return_pct(candles: list[dict], since: date) -> tuple[float | None, date | None]:
    """Returns (return_pct, actual_window_start). actual_window_start can
    be later than `since` if the OHLC history doesn't reach back that
    far — the 1y ceiling, not a bug."""
    in_window = [c for c in candles if datetime.fromisoformat(c["datetime_ist"]).date() >= since]
    if not in_window:
        in_window = candles
    if len(in_window) < 2:
        return None, None
    start_close = in_window[0]["close"]
    end_close = in_window[-1]["close"]
    actual_start = datetime.fromisoformat(in_window[0]["datetime_ist"]).date()
    if not start_close:
        return None, None
    return (end_close - start_close) / start_close * 100, actual_start


def _fd_equivalent_pct(since: date, today: date) -> float:
    days_held = (today - since).days
    return FD_ANNUAL_RATE_PCT * (days_held / 365)


async def compute_benchmark(db: Session, holding: Holding, nifty_candles: list[dict]) -> dict | None:
    if not holding.isin:
        return None
    buy_trade = _earliest_buy_trade(db, holding.isin)
    if buy_trade is None:
        return None

    today = datetime.now(timezone.utc).date()
    nifty_return_pct, actual_window_start = _nifty_return_pct(nifty_candles, buy_trade.trade_date)
    if nifty_return_pct is None or actual_window_start is None:
        return None

    window_capped = actual_window_start > buy_trade.trade_date
    fd_return_pct = _fd_equivalent_pct(actual_window_start, today)

    # holding.pnl_pct blends every buy lot at avg_cost — not a single-lot
    # return, and its implied start may predate buy_trade.trade_date if
    # the Trade Book import doesn't cover the true first purchase. Same
    # class of approximation task 22's LTCG-crossing suggestion already
    # documents; not re-solved here (that's real FIFO lot logic, out of
    # scope per task 20/22's own findings).
    holding_return_pct = holding.pnl_pct
    underperformed_both = holding_return_pct < nifty_return_pct and holding_return_pct < fd_return_pct

    window_note = (
        "NIFTY/FD compared over the last year only — OHLC history doesn't reach back to your "
        "actual buy date — "
        if window_capped
        else ""
    )
    return {
        "symbol": holding.symbol,
        "isin": holding.isin,
        "buy_date": buy_trade.trade_date.isoformat(),
        "window_start": actual_window_start.isoformat(),
        "window_capped_by_ohlc_history": window_capped,
        "holding_return_pct": round(holding_return_pct, 2),
        "nifty_return_pct": round(nifty_return_pct, 2),
        "fd_equivalent_return_pct": round(fd_return_pct, 2),
        "underperformed_both": underperformed_both,
        "reasoning": (
            f"{holding.symbol}: {holding_return_pct:+.1f}% since {buy_trade.trade_date} — {window_note}"
            f"vs NIFTY 50 {nifty_return_pct:+.1f}% and an FD-equivalent {fd_return_pct:+.1f}% "
            "over the same window."
        ),
        "data_source": "indmoney_mcp:get_indian_stocks_ohlc,trade_book_import",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


async def get_benchmarks(db: Session) -> list[dict]:
    holdings = db.query(Holding).filter(Holding.source == "api").all()
    nifty_ohlc = await call_tool("get_indian_stocks_ohlc", {"ind_key": NIFTY_IND_KEY, "interval": "1day", "lookback": "1y"})
    nifty_candles = nifty_ohlc.get("candles", [])

    results = []
    for h in holdings:
        result = await compute_benchmark(db, h, nifty_candles)
        if result is not None:
            results.append(result)
    return results
