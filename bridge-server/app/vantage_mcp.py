"""Vantage's own MCP server (task 26, planning-phase2.md §4) — co-hosted inside
bridge-server via streamable-HTTP, not a separate stdio child of `claude`
(that architectural distinction is what lets a future runner bridge tool
calls onto the same process's state, unlike a subprocess with no shared
memory). Every read tool below wraps an existing, already-verified function
directly — no logic duplicated, no HTTP round-trip back into this same
process. The one write tool (set_threshold) only ever touches the local
Threshold table; it never reads PAYTMMONEY_*/INDMONEY_* credentials or calls
a broker endpoint, so invariant #1 (read-only to the broker, forever) holds
trivially for everything exposed here.

MCP tools aren't FastAPI request handlers, so they don't get `Depends`
injection — each tool opens its own SessionLocal(), mirroring app.db.get_db's
own open/close pattern."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.behavioral import (
    compute_averaging_down as _compute_averaging_down,
    compute_disposition_effect as _compute_disposition_effect,
    compute_win_loss_asymmetry as _compute_win_loss_asymmetry,
)
from app.db import SessionLocal
from app.decisions import (
    get_decisions as _get_decisions,
    log_decision as _log_decision,
    set_decision_status as _set_decision_status,
)
from app.facts.benchmark import get_benchmarks as _get_benchmarks
from app.facts.volatility import get_volatility_stops as _get_volatility_stops
from app.routers.dashboard import get_dashboard as _get_dashboard
from app.routers.risk import get_risk as _get_risk
from app.routers.status import get_status as _get_status
from app.routers.thresholds import _upsert_threshold, list_thresholds as _list_thresholds
from app.routers.trend import get_trend as _get_trend
from app.run_context import current_run_key, current_touched_untrusted
from app.schemas.threshold import ThresholdIn
from app.tax.suggestions import get_tax_suggestions as _get_tax_suggestions
from app.thesis import add_thesis_entry as _add_thesis_entry, get_thesis_history as _get_thesis_history

mcp = FastMCP(name="vantage", streamable_http_path="/")


@mcp.tool()
def get_dashboard() -> dict[str, Any]:
    """Net worth (INR), per-holding rows, broker/asset-class/sector breakdowns,
    today's move, and threshold-breach flags — the same data as GET /api/dashboard."""
    with SessionLocal() as db:
        return _get_dashboard(db).model_dump(mode="json")


@mcp.tool()
def get_risk() -> dict[str, Any]:
    """Concentration flags (single-stock/sector over your configured limits) and
    India-vs-US region split — the same data as GET /api/risk."""
    with SessionLocal() as db:
        return _get_risk(db).model_dump(mode="json")


@mcp.tool()
def get_trend(days: int = 30) -> dict[str, Any]:
    """Portfolio net-worth trend over the trailing N days — the same data as
    GET /api/trend."""
    with SessionLocal() as db:
        return _get_trend(days=days, db=db).model_dump(mode="json")


@mcp.tool()
def get_thresholds() -> dict[str, Any]:
    """Current stop-loss/target thresholds for every holding — the same data as
    GET /api/thresholds."""
    with SessionLocal() as db:
        return _list_thresholds(db).model_dump(mode="json")


@mcp.tool()
def get_tax_suggestions() -> dict[str, Any]:
    """Loss-harvesting and LTCG-crossing-soon suggestions, parsed from
    PaytmMoney's own already-lot-matched Tax P&L / Harvesting exports (task 22).
    PaytmMoney-only — see planning-phase2.md §9."""
    with SessionLocal() as db:
        return {"suggestions": _get_tax_suggestions(db)}


@mcp.tool()
async def get_volatility_stops() -> dict[str, Any]:
    """Volatility-scaled stop-loss suggestions computed from real INDmoney OHLC
    (task 25). India-only. Can take ~1-2 minutes on a cold rate-limit window —
    INDmoney's MCP enforces a real 30 calls/min global limit and this tool
    needs up to 2 calls per holding."""
    with SessionLocal() as db:
        return {"suggestions": await _get_volatility_stops(db)}


@mcp.tool()
async def get_benchmark() -> dict[str, Any]:
    """Per-holding return vs NIFTY 50 and an FD-equivalent rate, over the actual
    holding period where a Trade Book buy date was imported (task 25).
    India-only, PaytmMoney-only — holdings with no imported buy trade are
    silently omitted, never given a fabricated buy date."""
    with SessionLocal() as db:
        return {"suggestions": await _get_benchmarks(db)}


@mcp.tool()
def get_status() -> dict[str, Any]:
    """Per-broker sync health, mode (live/mock), last successful sync, and any
    token-expiry warning — the same data as GET /api/status."""
    with SessionLocal() as db:
        return _get_status(db).model_dump(mode="json")


@mcp.tool()
def highlight_holding(symbol: str) -> dict[str, Any]:
    """Draw the user's attention to a specific holding in the dashboard UI —
    call this when you want to point at the holding you're discussing, not
    to read its data (use get_dashboard for that). Task 29's proof of the
    "UI action" mechanism (planning-phase2.md §4): this tool does no data
    work at all — its only purpose is to be a distinctly-named call the
    frontend recognizes on the WebSocket event stream and acts on locally
    (scroll-to + highlight), rather than rendering as a generic tool card."""
    return {"symbol": symbol, "action": "highlight"}


@mcp.tool()
def set_threshold(
    broker: str,
    symbol: str,
    stop_loss_pct: float | None = None,
    target_pct: float | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Set or update a holding's stop-loss/target threshold. stop_loss_pct must
    be negative, target_pct must be positive (e.g. stop_loss_pct=-7 for a 7%
    stop). Only fields you pass are changed — omitted fields keep their
    current value, they are never cleared implicitly. This writes only to
    Vantage's own local Threshold table; it never touches a broker or places
    any order — you still execute the stop/target manually in the broker app."""
    payload = ThresholdIn(
        broker=broker,
        symbol=symbol,
        stop_loss_pct=stop_loss_pct,
        target_pct=target_pct,
        notes=notes,
    )
    with SessionLocal() as db:
        threshold = _upsert_threshold(payload, db)
        return {
            "id": threshold.id,
            "broker": threshold.broker,
            "symbol": threshold.symbol,
            "stop_loss_pct": threshold.stop_loss_pct,
            "target_pct": threshold.target_pct,
            "notes": threshold.notes,
        }


@mcp.tool()
def add_thesis_entry(
    broker: str, symbol: str, text: str, conviction: int | None = None
) -> dict[str, Any]:
    """Log a new investment-thesis entry for a holding — task 33. Append-only:
    this always inserts a new, timestamped entry, it never overwrites a
    previous one, so scale-ins and an evolving view over time are each their
    own row. conviction, if given, should be 1-5. This is the fuller,
    versioned history for when a one-line note genuinely isn't enough (e.g.
    "why I'm still holding this after it dropped 18%") — it's separate from,
    and doesn't touch, the holding's short free-text notes field.

    Task 35: automatically tagged with this session's run_key and whether
    it has called WebFetch/WebSearch — never a caller-supplied argument, so
    the model can't simply claim "trusted" for a poisoned write."""
    with SessionLocal() as db:
        entry = _add_thesis_entry(
            db,
            broker=broker,
            symbol=symbol,
            text=text,
            conviction=conviction,
            run_session_id=current_run_key.get() or "",
            touched_untrusted_content=current_touched_untrusted.get(),
        )
        return {
            "id": entry.id,
            "broker": entry.broker,
            "symbol": entry.symbol,
            "text": entry.text,
            "conviction": entry.conviction,
            "created_at": entry.created_at.isoformat(),
            "touched_untrusted_content": entry.touched_untrusted_content,
        }


@mcp.tool()
def get_thesis_history(broker: str, symbol: str, include_quarantined: bool = False) -> dict[str, Any]:
    """Every thesis entry ever logged for a holding, oldest-first — task 33.
    Use this to see how the view on a holding has evolved, not just the
    latest snapshot. Returns an empty list if nothing has been logged yet,
    not an error.

    Task 35: by default omits an entry that touched untrusted web content
    and hasn't been human-reviewed yet (quarantined) — pass
    include_quarantined=True only for explicit review, never for routine
    reads, so a poisoned entry can't silently shape a future answer."""
    with SessionLocal() as db:
        entries = _get_thesis_history(db, broker=broker, symbol=symbol, include_quarantined=include_quarantined)
        return {
            "entries": [
                {
                    "id": e.id,
                    "broker": e.broker,
                    "symbol": e.symbol,
                    "text": e.text,
                    "conviction": e.conviction,
                    "created_at": e.created_at.isoformat(),
                    "touched_untrusted_content": e.touched_untrusted_content,
                    "reviewed": e.reviewed,
                }
                for e in entries
            ]
        }


def _serialize_decision(decision: Any) -> dict[str, Any]:
    return {
        "id": decision.id,
        "broker": decision.broker,
        "symbol": decision.symbol,
        "thesis_id": decision.thesis_id,
        "headline": decision.headline,
        "reference_price": decision.reference_price,
        "horizon_days": decision.horizon_days,
        "success_criterion_kind": decision.success_criterion_kind,
        "success_criterion_value": decision.success_criterion_value,
        "status": decision.status,
        "outcome": decision.outcome,
        "graded_at": decision.graded_at.isoformat() if decision.graded_at else None,
        "created_at": decision.created_at.isoformat(),
        "touched_untrusted_content": decision.touched_untrusted_content,
        "reviewed": decision.reviewed,
    }


@mcp.tool()
def log_decision(
    broker: str,
    symbol: str,
    headline: str,
    reference_price: float,
    horizon_days: int,
    success_criterion_kind: str,
    success_criterion_value: float,
    thesis_id: int | None = None,
) -> dict[str, Any]:
    """Log a concrete, checkable call — task 34. Call this when you make a
    real prediction (not every remark), e.g. "consider trimming — I'd
    expect this to underperform if it doesn't hold ₹X within 30 days."
    success_criterion_kind must be one of: price_above, price_below,
    pct_change_above, pct_change_below — a small closed vocabulary so
    grade_pending_decisions (via POST /api/decisions/grade) can mechanically
    check it later against real market prices once horizon_days has
    elapsed. reference_price should be the current price at the moment of
    the call. Optionally link it to a prior add_thesis_entry via thesis_id.
    Grading measures whether the prediction was correct — never whether you
    acted on it or what you actually did in the broker.

    Task 35: automatically tagged with this session's run_key and whether
    it has called WebFetch/WebSearch — never a caller-supplied argument, so
    the model can't simply claim "trusted" for a poisoned write."""
    with SessionLocal() as db:
        decision = _log_decision(
            db,
            broker=broker,
            symbol=symbol,
            headline=headline,
            reference_price=reference_price,
            horizon_days=horizon_days,
            success_criterion_kind=success_criterion_kind,
            success_criterion_value=success_criterion_value,
            thesis_id=thesis_id,
            run_session_id=current_run_key.get() or "",
            touched_untrusted_content=current_touched_untrusted.get(),
        )
        return _serialize_decision(decision)


@mcp.tool()
def set_decision_status(decision_id: int, status: str) -> dict[str, Any]:
    """Mark a previously logged call accepted or dismissed — task 34.
    status must be one of: logged, accepted, dismissed. This is always an
    explicit choice you make yourself; it is never inferred from
    conversation text. Independent of outcome, which only the grading job
    sets, once the horizon has elapsed."""
    with SessionLocal() as db:
        decision = _set_decision_status(db, decision_id=decision_id, status=status)
        if decision is None:
            return {"error": f"No decision_log row with id={decision_id}"}
        return _serialize_decision(decision)


@mcp.tool()
def get_decisions(
    broker: str | None = None, symbol: str | None = None, include_quarantined: bool = False
) -> dict[str, Any]:
    """Every logged call, newest-first — task 34. Optionally filter by
    broker and/or symbol. outcome is null until the grading job has run and
    horizon_days has elapsed for that row; status reflects only what you
    explicitly set via set_decision_status, defaulting to "logged".

    Task 35: by default omits a call that touched untrusted web content and
    hasn't been human-reviewed yet (quarantined) — pass
    include_quarantined=True only for explicit review, never for routine
    reads."""
    with SessionLocal() as db:
        decisions = _get_decisions(db, broker=broker, symbol=symbol, include_quarantined=include_quarantined)
        return {"decisions": [_serialize_decision(d) for d in decisions]}


@mcp.tool()
def get_behavioral_patterns() -> dict[str, Any]:
    """Pattern detection over your own real PaytmMoney trading history —
    task 37. Three concrete patterns, each with real numbers and the
    Trade/RealizedGain rows behind them identifiable:
    disposition_effect (do you hold losers longer than winners), averaging_down
    (how often you bought more of a stock while already below your average
    cost, and where), win_loss_asymmetry (win rate and gain/loss ratio from
    realized trades). PaytmMoney-only — INDmoney has no equivalent Trade Book
    export. A field is null where there isn't yet enough real data to compute
    it (e.g. no realized gains imported yet) — never a fabricated number."""
    with SessionLocal() as db:
        return {
            "disposition_effect": _compute_disposition_effect(db),
            "averaging_down": _compute_averaging_down(db),
            "win_loss_asymmetry": _compute_win_loss_asymmetry(db),
        }
