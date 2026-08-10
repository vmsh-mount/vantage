from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import HarvestingPosition, HarvestingSummary, RealizedGain, Trade
from app.schemas.statement import (
    HarvestingImportOut,
    TaxPnlImportOut,
    TradebookImportOut,
    TradebookSkippedRow,
)
from app.statements.harvesting import HarvestingParseError, parse_harvesting
from app.statements.tax_pnl import TaxPnlParseError, parse_tax_pnl
from app.statements.tradebook import TradebookParseError, parse_tradebook

router = APIRouter()

BROKER = "paytmmoney"  # only broker supported this phase — see planning-phase2.md


@router.post("/api/statements/tradebook", response_model=TradebookImportOut)
async def import_tradebook(file: UploadFile = File(...), db: Session = Depends(get_db)) -> TradebookImportOut:
    content = await file.read()
    try:
        rows = parse_tradebook(content)
    except TradebookParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    existing_order_numbers = {t.order_number for t in db.query(Trade.order_number).filter_by(broker=BROKER).all()}

    imported = 0
    duplicates_skipped = 0
    skipped: list[TradebookSkippedRow] = []
    seen_this_upload: set[str] = set()

    for row in rows:
        order_number = row["order_number"]
        if order_number in existing_order_numbers or order_number in seen_this_upload:
            duplicates_skipped += 1
            continue
        seen_this_upload.add(order_number)
        db.add(
            Trade(
                broker=BROKER,
                trade_date=row["trade_date"],
                script_code=row["script_code"],
                isin=row["isin"],
                exchange=row["exchange"],
                product_type=row["product_type"],
                txn_type=row["txn_type"],
                quantity=row["quantity"],
                price=row["price"],
                brokerage=row["brokerage"],
                ett=row["ett"],
                gst=row["gst"],
                stt=row["stt"],
                sebi=row["sebi"],
                stamp_duty=row["stamp_duty"],
                order_number=order_number,
                trade_number=row["trade_number"],
                trade_time=row["trade_time"],
            )
        )
        imported += 1

    db.commit()
    return TradebookImportOut(imported=imported, duplicates_skipped=duplicates_skipped, skipped=skipped)


@router.post("/api/statements/tax-pnl", response_model=TaxPnlImportOut)
async def import_tax_pnl(file: UploadFile = File(...), db: Session = Depends(get_db)) -> TaxPnlImportOut:
    content = await file.read()
    try:
        financial_year, lots = parse_tax_pnl(content)
    except TaxPnlParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    previous = db.query(RealizedGain).filter_by(broker=BROKER, financial_year=financial_year)
    previous_count = previous.count()
    previous.delete(synchronize_session=False)

    for lot in lots:
        db.add(RealizedGain(broker=BROKER, financial_year=financial_year, **lot))

    db.commit()
    return TaxPnlImportOut(
        financial_year=financial_year,
        lots_imported=len(lots),
        previous_lots_replaced=previous_count,
    )


@router.post("/api/statements/harvesting", response_model=HarvestingImportOut)
async def import_harvesting(file: UploadFile = File(...), db: Session = Depends(get_db)) -> HarvestingImportOut:
    content = await file.read()
    try:
        summary, positions = parse_harvesting(content)
    except HarvestingParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    as_on_date = summary["as_on_date"]

    previous_positions = db.query(HarvestingPosition).filter_by(broker=BROKER, as_on_date=as_on_date)
    previous_count = previous_positions.count()
    previous_positions.delete(synchronize_session=False)
    db.query(HarvestingSummary).filter_by(broker=BROKER, as_on_date=as_on_date).delete(synchronize_session=False)

    db.add(HarvestingSummary(broker=BROKER, **summary))
    for position in positions:
        db.add(HarvestingPosition(broker=BROKER, as_on_date=as_on_date, **position))

    db.commit()
    return HarvestingImportOut(
        as_on_date=str(as_on_date),
        positions_imported=len(positions),
        previous_positions_replaced=previous_count,
    )
