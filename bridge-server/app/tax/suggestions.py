"""Turns the PaytmMoney tax data already imported (task 21) into dated
suggestions. Deliberately not a tax-lot engine — PaytmMoney's own exports
already carry the FIFO-matched realized gains and the harvestable amounts;
this module only adds timing and framing on top. See docs/tasks/22-tax-
suggestions.md.

No tax-rate percentage is ever asserted in generated text: rates aren't in
the imported data, and citing one risks going stale if it changes."""

import calendar
from datetime import date

from sqlalchemy.orm import Session

from app.models import HarvestingPosition, HarvestingSummary, Holding, Trade

BROKER = "paytmmoney"
LTCG_CROSSING_HORIZON_DAYS = 60


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _financial_year_end(today: date) -> date:
    """Indian FY runs 1 Apr – 31 Mar. Returns the end date of the FY today
    falls in."""
    year = today.year if today.month < 4 else today.year + 1
    return date(year, 3, 31)


def _harvesting_suggestions(db: Session, today: date) -> list[dict]:
    latest_summary = (
        db.query(HarvestingSummary).filter_by(broker=BROKER).order_by(HarvestingSummary.as_on_date.desc()).first()
    )
    if latest_summary is None:
        return []

    positions = (
        db.query(HarvestingPosition)
        .filter_by(broker=BROKER, as_on_date=latest_summary.as_on_date)
        .all()
    )

    fy_end = _financial_year_end(today)
    days_to_fy_end = (fy_end - today).days

    suggestions = []
    for p in positions:
        if p.kind in ("loss_offset_short_term", "loss_offset_long_term"):
            term = "short-term" if p.kind == "loss_offset_short_term" else "long-term"
            suggestions.append(
                {
                    "kind": "harvest_loss",
                    "isin": p.isin,
                    "scrip_name": p.scrip_name,
                    "amount_inr": abs(p.unrealized_pnl),
                    "headline": (
                        f"{p.scrip_name} is sitting at a ₹{abs(p.unrealized_pnl):,.2f} unrealized loss — "
                        f"booking it before {fy_end.strftime('%d %b %Y')} ({days_to_fy_end} days left this "
                        f"financial year) can offset {term} gains you've already realized."
                    ),
                }
            )
        elif p.kind == "gain_opportunity_long_term":
            suggestions.append(
                {
                    "kind": "harvest_gain",
                    "isin": p.isin,
                    "scrip_name": p.scrip_name,
                    "amount_inr": p.unrealized_pnl,
                    "headline": (
                        f"{p.scrip_name} has a ₹{p.unrealized_pnl:,.2f} long-term unrealized gain — booking it "
                        f"before {fy_end.strftime('%d %b %Y')} uses this year's ₹1.25L tax-free LTCG bucket "
                        f"(₹{latest_summary.lt_gain_harvest_opportunity:,.2f} of headroom left, per PaytmMoney's "
                        f"own report)."
                    ),
                }
            )
    return suggestions


def _ltcg_crossing_suggestions(db: Session, today: date) -> list[dict]:
    holdings = db.query(Holding).filter(Holding.broker == BROKER, Holding.source == "api", Holding.isin.isnot(None)).all()

    suggestions = []
    for h in holdings:
        earliest_buy = (
            db.query(Trade)
            .filter_by(broker=BROKER, isin=h.isin, txn_type="BUY")
            .order_by(Trade.trade_date.asc())
            .first()
        )
        # No imported trade history for this ISIN — don't guess a crossing
        # date from nothing (task 22 acceptance criteria).
        if earliest_buy is None:
            continue

        crossing_date = _add_months(earliest_buy.trade_date, 12)
        days_remaining = (crossing_date - today).days
        if 0 < days_remaining <= LTCG_CROSSING_HORIZON_DAYS:
            suggestions.append(
                {
                    "kind": "ltcg_crossing_soon",
                    "isin": h.isin,
                    "scrip_name": h.symbol,
                    "amount_inr": None,
                    "headline": (
                        f"{h.symbol}'s earliest imported buy ({earliest_buy.trade_date.strftime('%d %b %Y')}) "
                        f"crosses into long-term treatment on {crossing_date.strftime('%d %b %Y')} "
                        f"({days_remaining} days) — selling after that date instead of now shifts this lot "
                        f"from short-term to long-term capital gains treatment. Based on the earliest trade "
                        f"actually imported for this ISIN, not necessarily your true first purchase."
                    ),
                }
            )
    return suggestions


def get_tax_suggestions(db: Session, today: date | None = None) -> list[dict]:
    today = today or date.today()
    return _harvesting_suggestions(db, today) + _ltcg_crossing_suggestions(db, today)
