"""Task 37 (planning-phase2.md §7.1): pattern detection over your own real
trading history — the one Half B piece buildable on task 21 alone, per the
plan's own note ("the mirror needs only task 21 + a surface"). Three
concrete, mechanically-computable patterns, each with the real Trade/
RealizedGain rows behind it identifiable (provenance, invariant #5) — no
vague "you seem to..." without a number backing it up, matching every
other fact-tool in this project.

PaytmMoney-only, same explicit scope boundary as tasks 21/22/25's benchmark
(planning-phase2.md §9) — INDmoney has no equivalent Trade Book export."""

from collections import defaultdict
from statistics import mean

from sqlalchemy.orm import Session

from app.models import RealizedGain, Trade

BROKER = "paytmmoney"

# Below this, a running position quantity is treated as fully closed —
# guards against float residue from repeated weighted-average subtraction
# ever being mistaken for "still holding a sliver."
QTY_EPSILON = 1e-6


def compute_disposition_effect(db: Session) -> dict:
    """Average holding period (days) for realized winners vs. realized
    losers — the classic behavioral-finance question: do you hold losers
    longer than winners, hoping they recover? Computed directly from
    PaytmMoney's own already lot-matched Tax P&L rows (task 21); no FIFO
    logic re-derived here. Lots with exact-zero P&L count as neither a
    winner nor a loser."""
    gains = db.query(RealizedGain).filter_by(broker=BROKER).all()
    winners = [g for g in gains if g.net_realized_pnl > 0]
    losers = [g for g in gains if g.net_realized_pnl < 0]

    def _avg_hold_days(rows: list[RealizedGain]) -> float | None:
        if not rows:
            return None
        return mean((r.sell_date - r.buy_date).days for r in rows)

    winner_days = _avg_hold_days(winners)
    loser_days = _avg_hold_days(losers)

    return {
        "winners_count": len(winners),
        "losers_count": len(losers),
        "avg_holding_days_winners": round(winner_days, 1) if winner_days is not None else None,
        "avg_holding_days_losers": round(loser_days, 1) if loser_days is not None else None,
        "holds_losers_longer": (
            loser_days > winner_days if winner_days is not None and loser_days is not None else None
        ),
        "data_source": "realized_gains (PaytmMoney Tax P&L import, task 21)",
    }


def compute_averaging_down(db: Session) -> dict:
    """How often a symbol received a 2nd-or-later BUY while its running,
    weighted-average cost (from BUYs on the currently-open position only)
    was already above that BUY's own price — buying more of something
    that's now cheaper than what you'd already paid on average.

    A SELL reduces the running position at its current average cost
    (weighted-average costing, not FIFO — this module doesn't need lot-
    level attribution, just a running cost basis). Once a position's
    tracked quantity returns to ~0, the *next* BUY starts a fresh average
    rather than being compared against a closed position's stale cost
    basis — an isin whose only Trade Book row is a SELL (a pre-existing
    position opened before the import window) never accumulates a
    negative running quantity; it's correctly treated as "no position
    tracked here yet," not a bug."""
    trades = db.query(Trade).filter_by(broker=BROKER).order_by(Trade.isin, Trade.trade_date, Trade.id).all()
    by_isin: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        by_isin[t.isin].append(t)

    events: list[dict] = []
    for isin, isin_trades in by_isin.items():
        running_qty = 0.0
        running_cost = 0.0
        for t in isin_trades:
            if t.txn_type == "BUY":
                if running_qty > QTY_EPSILON:
                    avg_cost = running_cost / running_qty
                    if avg_cost > t.price:
                        events.append(
                            {
                                "isin": isin,
                                "trade_date": t.trade_date.isoformat(),
                                "avg_cost_before": round(avg_cost, 4),
                                "buy_price": t.price,
                            }
                        )
                running_qty += t.quantity
                running_cost += t.quantity * t.price
            elif t.txn_type == "SELL" and running_qty > QTY_EPSILON:
                avg_cost = running_cost / running_qty
                sell_qty = min(t.quantity, running_qty)
                running_cost -= avg_cost * sell_qty
                running_qty -= sell_qty

    symbols_with_multiple_buys = sum(
        1 for isin_trades in by_isin.values() if sum(1 for t in isin_trades if t.txn_type == "BUY") > 1
    )

    return {
        "event_count": len(events),
        "events": events,
        "symbols_with_multiple_buys": symbols_with_multiple_buys,
        "data_source": "trades (PaytmMoney Trade Book import, task 21)",
    }


def compute_win_loss_asymmetry(db: Session) -> dict:
    """Win rate and the ratio of average realized gain to average realized
    loss, from PaytmMoney's own lot-matched Tax P&L rows (task 21)."""
    gains = db.query(RealizedGain).filter_by(broker=BROKER).all()
    wins = [g.net_realized_pnl for g in gains if g.net_realized_pnl > 0]
    losses = [g.net_realized_pnl for g in gains if g.net_realized_pnl < 0]
    breakeven_count = sum(1 for g in gains if g.net_realized_pnl == 0)

    win_rate = len(wins) / (len(wins) + len(losses)) if (wins or losses) else None
    avg_gain = mean(wins) if wins else None
    avg_loss = mean(abs(v) for v in losses) if losses else None
    gain_loss_ratio = avg_gain / avg_loss if avg_gain is not None and avg_loss else None

    return {
        "closed_lots": len(gains),
        "wins_count": len(wins),
        "losses_count": len(losses),
        "breakeven_count": breakeven_count,
        "win_rate": round(win_rate, 3) if win_rate is not None else None,
        "win_rate_note": "excludes exact-breakeven lots from both numerator and denominator",
        "avg_realized_gain": round(avg_gain, 2) if avg_gain is not None else None,
        "avg_realized_loss": round(avg_loss, 2) if avg_loss is not None else None,
        "gain_loss_ratio": round(gain_loss_ratio, 2) if gain_loss_ratio is not None else None,
        "data_source": "realized_gains (PaytmMoney Tax P&L import, task 21)",
    }
