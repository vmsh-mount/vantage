from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.fx import get_usd_inr_rate
from app.models import Holding
from app.schemas.holding import HoldingNotesIn, HoldingOut
from app.schemas.manual_holding import (
    CsvImportIn,
    CsvImportOut,
    CsvImportSkippedRow,
    ManualHoldingIn,
)

router = APIRouter()

MANUAL_BROKER = "indmoney"
MANUAL_CURRENCY = "USD"
MANUAL_ASSET_CLASS = "us_equity"


def _apply_manual_fields(holding: Holding, payload: ManualHoldingIn, fx_rate: float) -> None:
    if payload.ltp is not None:
        ltp = payload.ltp
    elif holding.ltp is not None:
        # Editing without an explicit ltp: preserve whatever price was last set
        # rather than silently resetting it to avg_cost as a side effect of an
        # unrelated field change (e.g. a "just bumped my quantity" edit).
        ltp = holding.ltp
    else:
        # Creating: nothing to preserve yet, fresh baseline.
        ltp = payload.avg_cost
    market_value = payload.quantity * ltp

    holding.symbol = payload.symbol.upper()
    holding.exchange = payload.exchange.upper()
    holding.quantity = payload.quantity
    holding.avg_cost = payload.avg_cost
    holding.ltp = ltp
    # Never present for manual holdings — no live feed to derive a previous
    # close from (architecture.md's Data Model note). Setting this to ltp
    # would look like real close-price data to any future code that reads
    # HoldingOut.close_price without checking source=='manual' first — a
    # plausible mistake, and a worse failure mode than a missing field since
    # it'd silently compute a fabricated "no move today" instead of signaling
    # "no data."
    holding.close_price = None
    holding.currency = MANUAL_CURRENCY
    holding.market_value = market_value
    holding.market_value_inr = market_value * fx_rate
    holding.pnl_abs = (ltp - payload.avg_cost) * payload.quantity
    holding.pnl_pct = (ltp - payload.avg_cost) / payload.avg_cost * 100
    holding.sector = payload.sector
    holding.asset_class = MANUAL_ASSET_CLASS
    holding.source = "manual"


def _get_manual_holding_or_404(db: Session, holding_id: int) -> Holding:
    holding = db.get(Holding, holding_id)
    if holding is None or holding.source != "manual":
        raise HTTPException(status_code=404, detail="Manual holding not found")
    return holding


@router.post("/api/holdings/manual", response_model=HoldingOut, status_code=201)
def create_manual_holding(payload: ManualHoldingIn, db: Session = Depends(get_db)) -> Holding:
    symbol = payload.symbol.upper()
    existing = db.query(Holding).filter_by(broker=MANUAL_BROKER, symbol=symbol).one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A holding for {symbol} already exists — edit it instead of creating a duplicate.",
        )

    fx_rate = get_usd_inr_rate()
    holding = Holding(broker=MANUAL_BROKER, symbol=symbol)
    _apply_manual_fields(holding, payload, fx_rate)
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return holding


@router.put("/api/holdings/manual/{holding_id}", response_model=HoldingOut)
def update_manual_holding(holding_id: int, payload: ManualHoldingIn, db: Session = Depends(get_db)) -> Holding:
    holding = _get_manual_holding_or_404(db, holding_id)

    new_symbol = payload.symbol.upper()
    if new_symbol != holding.symbol:
        collision = db.query(Holding).filter_by(broker=MANUAL_BROKER, symbol=new_symbol).one_or_none()
        if collision is not None:
            raise HTTPException(
                status_code=409,
                detail=f"A holding for {new_symbol} already exists.",
            )

    fx_rate = get_usd_inr_rate()
    _apply_manual_fields(holding, payload, fx_rate)
    db.commit()
    db.refresh(holding)
    return holding


@router.delete("/api/holdings/manual/{holding_id}", status_code=204)
def delete_manual_holding(holding_id: int, db: Session = Depends(get_db)) -> None:
    holding = _get_manual_holding_or_404(db, holding_id)
    db.delete(holding)
    db.commit()


# Task 32 — deliberately separate from the manual-only CRUD endpoints above:
# notes apply to any holding regardless of source, not just manual ones.
@router.put("/api/holdings/{holding_id}/notes", response_model=HoldingOut)
def update_holding_notes(holding_id: int, payload: HoldingNotesIn, db: Session = Depends(get_db)) -> Holding:
    holding = db.get(Holding, holding_id)
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")
    # Empty string is a deliberate clear, same as None — no separate "blank
    # but not null" state to reason about later.
    holding.notes = payload.notes if payload.notes else None
    db.commit()
    db.refresh(holding)
    return holding


def _parse_csv_line(line: str) -> tuple[dict | None, str | None]:
    parts = [p.strip() for p in line.split(",")]
    symbol = (parts[0] if parts else "").upper()
    if not symbol:
        return None, "missing symbol"
    if len(parts) < 3:
        return None, "missing fields (need symbol, qty, avg_cost)"

    try:
        qty = float(parts[1])
    except ValueError:
        return None, f"invalid quantity: {parts[1]!r}"
    if qty <= 0:
        return None, "quantity must be positive"

    try:
        cost = float(parts[2])
    except ValueError:
        return None, f"invalid avg_cost: {parts[2]!r}"
    if cost <= 0:
        return None, "avg_cost must be positive"

    sector = parts[3] if len(parts) > 3 and parts[3] else "Uncategorized"
    return {"symbol": symbol, "quantity": qty, "avg_cost": cost, "sector": sector}, None


@router.post("/api/holdings/manual/import-csv", response_model=CsvImportOut)
def import_csv(payload: CsvImportIn, db: Session = Depends(get_db)) -> CsvImportOut:
    fx_rate = get_usd_inr_rate()
    imported: list[HoldingOut] = []
    skipped: list[CsvImportSkippedRow] = []
    seen_symbols: set[str] = set()

    existing_symbols = {
        h.symbol for h in db.query(Holding).filter_by(broker=MANUAL_BROKER).all()
    }

    for line_number, line in enumerate(payload.csv.splitlines(), start=1):
        if not line.strip():
            continue

        parsed, error = _parse_csv_line(line)
        if error:
            skipped.append(CsvImportSkippedRow(line_number=line_number, raw=line, reason=error))
            continue

        symbol = parsed["symbol"]
        if symbol in existing_symbols or symbol in seen_symbols:
            skipped.append(
                CsvImportSkippedRow(line_number=line_number, raw=line, reason=f"{symbol} already exists")
            )
            continue

        holding_in = ManualHoldingIn(
            symbol=symbol,
            quantity=parsed["quantity"],
            avg_cost=parsed["avg_cost"],
            sector=parsed["sector"],
        )
        holding = Holding(broker=MANUAL_BROKER, symbol=symbol)
        _apply_manual_fields(holding, holding_in, fx_rate)
        db.add(holding)
        seen_symbols.add(symbol)
        imported.append(holding)

    db.commit()
    for holding in imported:
        db.refresh(holding)

    return CsvImportOut(
        imported=[HoldingOut.model_validate(h) for h in imported],
        skipped=skipped,
    )
