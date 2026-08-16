"""Compass (docs/compass-prd.md §6.3): CRUD + pace progress for Milestone
rows. Business logic lives in app/milestones.py."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.milestones import (
    SUPPORTED_METRIC_TYPES,
    compute_milestone_progress,
    create_milestone,
    deactivate_milestone,
    list_milestones,
)
from app.schemas.milestone import MilestoneIn, MilestoneOut, MilestoneProgressOut, MilestonesListOut

router = APIRouter()


@router.get("/api/milestones", response_model=MilestonesListOut)
def get_milestones(db: Session = Depends(get_db)) -> MilestonesListOut:
    milestones = list_milestones(db)
    return MilestonesListOut(milestones=[MilestoneOut.model_validate(m) for m in milestones])


@router.post("/api/milestones", response_model=MilestoneOut, status_code=201)
def create_milestone_route(payload: MilestoneIn, db: Session = Depends(get_db)) -> MilestoneOut:
    if payload.metric_type not in SUPPORTED_METRIC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported metric_type {payload.metric_type!r}; must be one of {SUPPORTED_METRIC_TYPES}",
        )
    # net_worth's zero-or-negative case has no sane meaning ("reach ₹0
    # net worth by a date"); pnl_pct's does (break-even is 0, cutting a
    # loss further is negative) — see the model's own docstring.
    if payload.metric_type == "net_worth" and payload.target_value <= 0:
        raise HTTPException(status_code=400, detail="target_value must be positive for a net_worth milestone")
    milestone = create_milestone(
        db,
        name=payload.name,
        target_value=payload.target_value,
        target_date=payload.target_date,
        metric_type=payload.metric_type,
        rationale=payload.rationale,
    )
    return MilestoneOut.model_validate(milestone)


@router.delete("/api/milestones/{milestone_id}", status_code=204)
def delete_milestone_route(milestone_id: int, db: Session = Depends(get_db)) -> None:
    milestone = deactivate_milestone(db, milestone_id)
    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")


@router.get("/api/milestones/progress", response_model=list[MilestoneProgressOut])
def get_milestones_progress(db: Session = Depends(get_db)) -> list[dict]:
    return [compute_milestone_progress(db, m) for m in list_milestones(db)]
