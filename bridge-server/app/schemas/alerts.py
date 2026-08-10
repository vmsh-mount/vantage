from pydantic import BaseModel


class AlertItem(BaseModel):
    kind: str  # "stop_loss" | "mover"
    broker: str
    symbol: str
    severity: str  # "gain" | "loss"
    title: str


class AlertsOut(BaseModel):
    alerts: list[AlertItem]
