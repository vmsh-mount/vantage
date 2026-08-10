from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiCallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker: str
    endpoint: str
    status_code: int
    called_at: datetime
