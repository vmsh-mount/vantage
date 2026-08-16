"""Compass (docs/compass-prd.md §6.1): CRUD + progress for Goal rows.
Business logic lives in app/goals.py. Progress responses aren't a single
fixed schema — each metric_type's calculator returns its own shape
(contributions for price_return_pct, coverage for dividend_coverage, ...)
— so /progress is deliberately not pinned to one response_model."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.goals import SUPPORTED_METRIC_TYPES, compute_goal_progress, create_goal, deactivate_goal, list_goals
from app.schemas.goal import GoalIn, GoalOut, GoalsListOut

router = APIRouter()


@router.get("/api/goals", response_model=GoalsListOut)
def get_goals(db: Session = Depends(get_db)) -> GoalsListOut:
    goals = list_goals(db)
    return GoalsListOut(goals=[GoalOut.model_validate(g) for g in goals])


@router.post("/api/goals", response_model=GoalOut, status_code=201)
def create_goal_route(payload: GoalIn, db: Session = Depends(get_db)) -> GoalOut:
    if payload.metric_type not in SUPPORTED_METRIC_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported metric_type {payload.metric_type!r}; must be one of {SUPPORTED_METRIC_TYPES}",
        )
    goal = create_goal(
        db,
        name=payload.name,
        metric_type=payload.metric_type,
        target_value=payload.target_value,
        scope_type=payload.scope_type,
        scope_value=payload.scope_value,
        comparison=payload.comparison,
        period=payload.period,
        period_n=payload.period_n,
        rationale=payload.rationale,
    )
    return GoalOut.model_validate(goal)


@router.delete("/api/goals/{goal_id}", status_code=204)
def delete_goal_route(goal_id: int, db: Session = Depends(get_db)) -> None:
    goal = deactivate_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")


@router.get("/api/goals/progress")
def get_goals_progress(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [compute_goal_progress(db, g) for g in list_goals(db)]
