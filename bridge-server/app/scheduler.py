import logging
import threading
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.audit_log import log_api_call
from app.breakdowns import compute_breakdown_sums, compute_total_pnl
from app.config import settings
from app.db import SessionLocal
from app.digest import run_daily_digest
from app.integrations.base import NormalizedHolding
from app.integrations.fx import get_usd_inr_rate
from app.integrations.indmoney import IndmoneyClient
from app.integrations.paytmmoney import PaytmMoneyClient
from app.models import Holding, HoldingSnapshot, PortfolioSnapshot

logger = logging.getLogger("vantage.scheduler")

BROKER_CLIENTS = {
    "paytmmoney": PaytmMoneyClient(),
    "indmoney": IndmoneyClient(),
}
BROKER_ENDPOINT_PATHS = {
    "paytmmoney": "/holdings/v1/get-user-holdings-data",
    "indmoney": "/portfolio/holdings",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _endpoint_label(broker: str) -> str:
    mode = settings.paytmmoney_mode if broker == "paytmmoney" else settings.indmoney_mode
    return f"{mode}:{BROKER_ENDPOINT_PATHS[broker]}"


def _market_value_inr(market_value: float, currency: str, fx_rate: float | None) -> float:
    if currency == "INR":
        return market_value
    if fx_rate is None:
        raise ValueError("USD holding requires an FX rate to convert to INR, but none was available this tick")
    return market_value * fx_rate


def _upsert_holding(db, normalized: NormalizedHolding, fx_rate: float | None) -> None:
    existing = (
        db.query(Holding)
        .filter_by(broker=normalized.broker, symbol=normalized.symbol)
        .one_or_none()
    )
    values = dict(
        exchange=normalized.exchange,
        isin=normalized.isin,
        quantity=normalized.quantity,
        avg_cost=normalized.avg_cost,
        ltp=normalized.ltp,
        close_price=normalized.close_price,
        currency=normalized.currency,
        market_value=normalized.market_value,
        market_value_inr=_market_value_inr(normalized.market_value, normalized.currency, fx_rate),
        pnl_abs=normalized.pnl_abs,
        pnl_pct=normalized.pnl_pct,
        sector=normalized.sector,
        asset_class=normalized.asset_class,
        source="api",
        last_synced_at=_utcnow(),
    )
    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
    else:
        db.add(Holding(broker=normalized.broker, symbol=normalized.symbol, **values))


def _prune_stale_holdings(db, broker: str, live_symbols: set[str]) -> int:
    """Removes API-sourced Holding rows for `broker` that this sync's live
    response no longer reports — i.e. actually sold/removed at the broker.

    Real bug found live: _upsert_holding only ever adds or updates, never
    removes, so a holding inserted while INDMONEY_MODE=mock (a fixture row,
    ICICIBANK) survived silently forever after switching to real live
    credentials, indistinguishable from an actual current holding — it was
    inflating displayed net worth. The same gap would just as easily hide a
    real holding you'd actually sold. Only ever called on a non-empty
    response (see _sync_broker) — never touches source == "manual" rows,
    which no broker sync manages at all."""
    stale = (
        db.query(Holding)
        .filter_by(broker=broker, source="api")
        .filter(~Holding.symbol.in_(live_symbols))
        .all()
    )
    for holding in stale:
        logger.warning(
            "Pruning stale holding no longer reported by %s: %s (last seen %s)",
            broker,
            holding.symbol,
            holding.last_synced_at,
        )
        db.delete(holding)
    return len(stale)


def _sync_broker(db, broker: str, client, fx_rate: float | None) -> dict:
    endpoint = _endpoint_label(broker)
    try:
        holdings = client.fetch_holdings()
        for normalized in holdings:
            _upsert_holding(db, normalized, fx_rate)

        pruned = 0
        if holdings:
            # Only prune on a genuinely non-empty response — an empty list
            # is more likely a degraded/wrong API response than "you sold
            # everything," and silently deleting every holding on that
            # basis would be a worse bug than the stale-row one this fixes.
            live_symbols = {normalized.symbol for normalized in holdings}
            pruned = _prune_stale_holdings(db, broker, live_symbols)

        log_api_call(db, broker, endpoint, 200)
        return {"ok": True, "count": len(holdings), "pruned": pruned}
    except Exception as exc:
        status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 0
        log_api_call(db, broker, endpoint, status_code)
        logger.warning("Broker sync failed for %s: %s", broker, exc)
        return {"ok": False, "error": str(exc)}


def _refresh_manual_market_value_inr(db, fx_rate: float) -> None:
    for holding in db.query(Holding).filter_by(source="manual").all():
        holding.market_value_inr = _market_value_inr(holding.market_value, holding.currency, fx_rate)


def _write_snapshots(db) -> None:
    all_holdings = db.query(Holding).all()
    total_net_worth_inr = sum(h.market_value_inr for h in all_holdings)
    # Milestone's pnl_pct metric type (docs/compass-prd.md §6.3) reads this
    # trailing history the same way net_worth already does — no separate
    # pipeline, just one more column on the same snapshot.
    _, total_pnl_pct = compute_total_pnl(all_holdings)
    db.add(
        PortfolioSnapshot(
            total_net_worth_inr=total_net_worth_inr,
            total_pnl_pct=total_pnl_pct,
            breakdown_json=compute_breakdown_sums(all_holdings),
        )
    )
    for h in all_holdings:
        db.add(
            HoldingSnapshot(
                broker=h.broker,
                symbol=h.symbol,
                market_value_inr=h.market_value_inr,
                ltp=h.ltp,
                pnl_pct=h.pnl_pct,
            )
        )


# Guards against two syncs running at once — not just two manual /api/refresh
# calls racing each other, but the much more likely real collision: a user
# hitting "Refresh now" at the same moment the periodic interval tick fires,
# which needs no double-click or script, just ordinary timing. Both call
# paths go through this one function, so a single lock here protects both,
# rather than one guarding only the endpoint and leaving the scheduler's own
# tick free to collide with it (two concurrent SessionLocal()s against the
# same SQLite file otherwise risk a "database is locked" error).
_sync_lock = threading.Lock()


def run_sync_pipeline() -> dict | None:
    """The one sync tick. Callable directly — task 12's POST /api/refresh reuses
    this rather than duplicating it — or scheduled on an interval below.
    Returns None (never raises) if a sync was already in progress; callers
    should treat that as "try again shortly", not a failure."""
    if not _sync_lock.acquire(blocking=False):
        logger.info("Sync already in progress, skipping")
        return None
    try:
        db = SessionLocal()
        try:
            fx_rate: float | None = None
            try:
                fx_rate = get_usd_inr_rate()
            except Exception as exc:
                log_api_call(db, "fx", "frankfurter:usd-inr", 0)
                logger.warning("FX rate fetch failed, USD holdings' INR value won't refresh this tick: %s", exc)

            results = {
                broker: _sync_broker(db, broker, client, fx_rate)
                for broker, client in BROKER_CLIENTS.items()
            }
            if fx_rate is not None:
                _refresh_manual_market_value_inr(db, fx_rate)
            _write_snapshots(db)
            db.commit()
            return results
        finally:
            db.close()
    finally:
        _sync_lock.release()


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_sync_pipeline,
        "interval",
        minutes=settings.refresh_interval_minutes,
        id="sync_pipeline",
        next_run_time=_utcnow(),
    )
    # Explicit Asia/Kolkata rather than trusting the host OS's local tz — this
    # is an India-focused single-user app; the schedule shouldn't silently
    # shift if it ever runs on a machine set to a different timezone.
    _scheduler.add_job(
        run_daily_digest,
        CronTrigger(
            hour=settings.digest_send_hour,
            minute=settings.digest_send_minute,
            timezone="Asia/Kolkata",
        ),
        id="daily_digest",
    )
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
