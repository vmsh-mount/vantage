"""Compass (docs/compass-prd.md §8): CRUD for the manual Dividend log — the
only way dividend data enters Vantage, since no broker API exposes it (see
the Dividend model's own docstring for the live research trace)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Dividend
from app.schemas.dividend import DividendIn, DividendOut, DividendsListOut

router = APIRouter()


def _get_dividend_or_404(db: Session, dividend_id: int) -> Dividend:
    dividend = db.get(Dividend, dividend_id)
    if dividend is None:
        raise HTTPException(status_code=404, detail="Dividend entry not found")
    return dividend


@router.get("/api/dividends", response_model=DividendsListOut)
def list_dividends(
    broker: str | None = None, symbol: str | None = None, db: Session = Depends(get_db)
) -> DividendsListOut:
    query = db.query(Dividend)
    if broker is not None:
        query = query.filter_by(broker=broker)
    if symbol is not None:
        query = query.filter_by(symbol=symbol)
    dividends = query.order_by(Dividend.payment_date.desc(), Dividend.id.desc()).all()
    return DividendsListOut(dividends=[DividendOut.model_validate(d) for d in dividends])


@router.post("/api/dividends", response_model=DividendOut, status_code=201)
def create_dividend(payload: DividendIn, db: Session = Depends(get_db)) -> Dividend:
    dividend = Dividend(
        broker=payload.broker,
        symbol=payload.symbol.upper(),
        amount_inr=payload.amount_inr,
        payment_date=payload.payment_date,
        notes=payload.notes,
    )
    db.add(dividend)
    db.commit()
    db.refresh(dividend)
    return dividend


@router.put("/api/dividends/{dividend_id}", response_model=DividendOut)
def update_dividend(dividend_id: int, payload: DividendIn, db: Session = Depends(get_db)) -> Dividend:
    dividend = _get_dividend_or_404(db, dividend_id)
    dividend.broker = payload.broker
    dividend.symbol = payload.symbol.upper()
    dividend.amount_inr = payload.amount_inr
    dividend.payment_date = payload.payment_date
    dividend.notes = payload.notes
    db.commit()
    db.refresh(dividend)
    return dividend


@router.delete("/api/dividends/{dividend_id}", status_code=204)
def delete_dividend(dividend_id: int, db: Session = Depends(get_db)) -> None:
    dividend = _get_dividend_or_404(db, dividend_id)
    db.delete(dividend)
    db.commit()
