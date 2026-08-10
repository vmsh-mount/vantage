from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RiskSettings
from app.schemas.risk_settings import RiskSettingsIn, RiskSettingsOut

router = APIRouter()


def _get_or_create_settings(db: Session) -> RiskSettings:
    settings_row = db.query(RiskSettings).first()
    if settings_row is None:
        settings_row = RiskSettings()
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


@router.get("/api/settings/risk", response_model=RiskSettingsOut)
def get_risk_settings(db: Session = Depends(get_db)) -> RiskSettings:
    return _get_or_create_settings(db)


@router.put("/api/settings/risk", response_model=RiskSettingsOut)
def update_risk_settings(payload: RiskSettingsIn, db: Session = Depends(get_db)) -> RiskSettings:
    settings_row = _get_or_create_settings(db)

    if payload.concentration_stock_pct is not None:
        settings_row.concentration_stock_pct = payload.concentration_stock_pct
    if payload.concentration_sector_pct is not None:
        settings_row.concentration_sector_pct = payload.concentration_sector_pct

    # Single-slider UX (matches the prototype): setting one side of the
    # India/US target derives the other, so the two can never drift apart.
    if payload.target_india_pct is not None:
        settings_row.target_india_pct = payload.target_india_pct
        settings_row.target_us_pct = 100 - payload.target_india_pct
    elif payload.target_us_pct is not None:
        settings_row.target_us_pct = payload.target_us_pct
        settings_row.target_india_pct = 100 - payload.target_us_pct

    db.commit()
    db.refresh(settings_row)
    return settings_row
