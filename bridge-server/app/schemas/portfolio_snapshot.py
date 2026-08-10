from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PortfolioSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    captured_at: datetime
    total_net_worth_inr: float
    breakdown_json: dict
