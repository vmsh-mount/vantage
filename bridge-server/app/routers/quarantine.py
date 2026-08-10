"""Task 35: the human-review surface for quarantined Thesis/DecisionLog
rows — a row that touched untrusted web content and hasn't been reviewed
yet. Deliberately the only way `reviewed` ever flips to True; no automated
review/approval logic exists anywhere in this project (see
docs/tasks/35-memory-poisoning-defenses.md's Out of scope)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DecisionLog, Thesis
from app.schemas.quarantine import QuarantineOut, QuarantineReviewOut

router = APIRouter()

_TABLES = {"theses": Thesis, "decision_log": DecisionLog}


@router.get("/api/quarantine", response_model=QuarantineOut)
def list_quarantine(db: Session = Depends(get_db)) -> QuarantineOut:
    theses = db.query(Thesis).filter_by(touched_untrusted_content=True, reviewed=False).all()
    decisions = db.query(DecisionLog).filter_by(touched_untrusted_content=True, reviewed=False).all()
    return QuarantineOut(
        theses=[
            {
                "id": t.id,
                "broker": t.broker,
                "symbol": t.symbol,
                "text": t.text,
                "conviction": t.conviction,
                "run_session_id": t.run_session_id,
                "created_at": t.created_at,
            }
            for t in theses
        ],
        decisions=[
            {
                "id": d.id,
                "broker": d.broker,
                "symbol": d.symbol,
                "headline": d.headline,
                "run_session_id": d.run_session_id,
                "created_at": d.created_at,
            }
            for d in decisions
        ],
    )


@router.post("/api/quarantine/{table}/{item_id}/review", response_model=QuarantineReviewOut)
def review_quarantined(table: str, item_id: int, db: Session = Depends(get_db)) -> QuarantineReviewOut:
    model = _TABLES.get(table)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Unknown quarantine table {table!r}")
    row = db.query(model).filter_by(id=item_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No {table} row with id={item_id}")
    row.reviewed = True
    db.commit()
    db.refresh(row)
    return QuarantineReviewOut(table=table, id=row.id, reviewed=row.reviewed)
