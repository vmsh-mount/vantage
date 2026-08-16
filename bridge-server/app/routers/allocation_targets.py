"""Compass (docs/compass-prd.md §6.2): CRUD + progress for AllocationTarget
rows. Business logic (upsert/list/deactivate/progress) lives in
app/allocation_targets.py — this router is thin, matching the split every
other Compass piece uses."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.allocation_targets import (
    SUPPORTED_DIMENSIONS,
    compute_allocation_progress,
    compute_dimension_breakdown,
    deactivate_allocation_target,
    list_allocation_targets,
    upsert_allocation_target,
)
from app.db import get_db
from app.schemas.allocation_target import (
    AllocationProgressOut,
    AllocationTargetIn,
    AllocationTargetOut,
    AllocationTargetsListOut,
    DimensionBreakdownOut,
)

router = APIRouter()


@router.get("/api/allocation-targets", response_model=AllocationTargetsListOut)
def get_allocation_targets(
    dimension: str | None = Query(default=None), db: Session = Depends(get_db)
) -> AllocationTargetsListOut:
    targets = list_allocation_targets(db, dimension=dimension)
    return AllocationTargetsListOut(targets=[AllocationTargetOut.model_validate(t) for t in targets])


@router.post("/api/allocation-targets", response_model=AllocationTargetOut, status_code=201)
def create_or_update_allocation_target(payload: AllocationTargetIn, db: Session = Depends(get_db)) -> AllocationTargetOut:
    if payload.dimension not in SUPPORTED_DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported dimension {payload.dimension!r}; must be one of {SUPPORTED_DIMENSIONS}",
        )
    target = upsert_allocation_target(
        db,
        dimension=payload.dimension,
        bucket=payload.bucket,
        target_pct=payload.target_pct,
        tolerance_pct=payload.tolerance_pct,
        rationale=payload.rationale,
    )
    return AllocationTargetOut.model_validate(target)


@router.delete("/api/allocation-targets/{target_id}", status_code=204)
def delete_allocation_target(target_id: int, db: Session = Depends(get_db)) -> None:
    target = deactivate_allocation_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Allocation target not found")


@router.get("/api/allocation-targets/progress", response_model=AllocationProgressOut)
def get_allocation_progress(dimension: str = Query(...), db: Session = Depends(get_db)) -> AllocationProgressOut:
    if dimension not in SUPPORTED_DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported dimension {dimension!r}; must be one of {SUPPORTED_DIMENSIONS}",
        )
    progress = compute_allocation_progress(db, dimension)
    return AllocationProgressOut(dimension=dimension, progress=progress)


@router.get("/api/allocation-targets/current-breakdown", response_model=DimensionBreakdownOut)
def get_dimension_breakdown(dimension: str = Query(...), db: Session = Depends(get_db)) -> DimensionBreakdownOut:
    """Real current allocation for every bucket actually held — independent
    of whether a target exists yet. Powers the add-target form's "current:
    X%" hint (app/allocation_targets.py's compute_dimension_breakdown)."""
    if dimension not in SUPPORTED_DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported dimension {dimension!r}; must be one of {SUPPORTED_DIMENSIONS}",
        )
    return DimensionBreakdownOut(dimension=dimension, breakdown=compute_dimension_breakdown(db, dimension))
