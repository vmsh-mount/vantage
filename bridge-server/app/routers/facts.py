from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.facts.benchmark import get_benchmarks
from app.facts.volatility import get_volatility_stops
from app.schemas.facts import BenchmarkOut, VolatilityStopsOut

router = APIRouter()


@router.get("/api/facts/volatility-stops", response_model=VolatilityStopsOut)
async def volatility_stops(db: Session = Depends(get_db)) -> VolatilityStopsOut:
    return VolatilityStopsOut(suggestions=await get_volatility_stops(db))


@router.get("/api/facts/benchmark", response_model=BenchmarkOut)
async def benchmark(db: Session = Depends(get_db)) -> BenchmarkOut:
    return BenchmarkOut(suggestions=await get_benchmarks(db))
