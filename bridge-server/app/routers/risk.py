from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.breakdowns import compute_net_worth_inr
from app.db import get_db
from app.models import Holding, RiskSettings
from app.regions import region_for_exchange
from app.schemas.risk import ConcentrationFlag, RegionSplit, RiskOut

router = APIRouter()


@router.get("/api/risk", response_model=RiskOut)
def get_risk(db: Session = Depends(get_db)) -> RiskOut:
    holdings = db.query(Holding).all()
    net_worth_inr = compute_net_worth_inr(holdings)
    settings_row = db.query(RiskSettings).first() or RiskSettings()

    flags: list[ConcentrationFlag] = []
    if net_worth_inr:
        # Aggregate by symbol, not per-Holding-row — the same stock split across
        # two brokers (e.g. RELIANCE via both PaytmMoney and INDmoney) is one real
        # concentration exposure, not two smaller ones each below the limit.
        by_symbol: dict[str, float] = {}
        for h in holdings:
            by_symbol[h.symbol] = by_symbol.get(h.symbol, 0) + h.market_value_inr
        for symbol, value in by_symbol.items():
            pct = value / net_worth_inr * 100
            if pct >= settings_row.concentration_stock_pct:
                flags.append(
                    ConcentrationFlag(
                        kind="stock",
                        label=symbol,
                        pct=pct,
                        limit_pct=settings_row.concentration_stock_pct,
                    )
                )

        by_sector: dict[str, float] = {}
        for h in holdings:
            sector = h.sector or "Unknown"
            by_sector[sector] = by_sector.get(sector, 0) + h.market_value_inr
        for sector, value in by_sector.items():
            pct = value / net_worth_inr * 100
            if pct >= settings_row.concentration_sector_pct:
                flags.append(
                    ConcentrationFlag(
                        kind="sector",
                        label=sector,
                        pct=pct,
                        limit_pct=settings_row.concentration_sector_pct,
                    )
                )

    india_value = sum(h.market_value_inr for h in holdings if region_for_exchange(h.exchange) == "india")
    us_value = net_worth_inr - india_value
    india_pct = (india_value / net_worth_inr * 100) if net_worth_inr else 0.0
    us_pct = (us_value / net_worth_inr * 100) if net_worth_inr else 0.0

    drift_pct = None
    if settings_row.target_india_pct is not None:
        drift_pct = india_pct - settings_row.target_india_pct

    return RiskOut(
        concentration_flags=flags,
        region_split=RegionSplit(
            india_pct=india_pct,
            us_pct=us_pct,
            target_india_pct=settings_row.target_india_pct,
            target_us_pct=settings_row.target_us_pct,
            drift_pct=drift_pct,
        ),
    )
