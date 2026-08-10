"""Task 34: the one REST surface for the decision log — triggering grading.
Reading/writing DecisionLog rows themselves is agent-only (app/vantage_mcp.py's
log_decision/set_decision_status/get_decisions), matching task 33's own
scope call; there is deliberately no CRUD here."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.grading import grade_pending_decisions
from app.schemas.decision_log import GradeDecisionsOut

router = APIRouter()


@router.post("/api/decisions/grade", response_model=GradeDecisionsOut)
async def grade_decisions(db: Session = Depends(get_db)) -> GradeDecisionsOut:
    graded = await grade_pending_decisions(db)
    return GradeDecisionsOut(graded=graded)
