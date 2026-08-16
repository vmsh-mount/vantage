"""Compass (docs/compass-prd.md §11): the one whole-feature summary
endpoint. Business logic lives in app/compass.py, shared with the MCP
bundling tool and the digest's summary line."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.compass import compute_compass_summary
from app.db import get_db

router = APIRouter()


@router.get("/api/compass/summary")
def get_compass_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return compute_compass_summary(db)
