from datetime import datetime

from pydantic import BaseModel


class QuarantinedThesis(BaseModel):
    id: int
    broker: str
    symbol: str
    text: str
    conviction: int | None
    run_session_id: str
    created_at: datetime


class QuarantinedDecision(BaseModel):
    id: int
    broker: str
    symbol: str
    headline: str
    run_session_id: str
    created_at: datetime


class QuarantineOut(BaseModel):
    theses: list[QuarantinedThesis]
    decisions: list[QuarantinedDecision]


class QuarantineReviewOut(BaseModel):
    table: str
    id: int
    reviewed: bool
