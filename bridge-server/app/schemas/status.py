from datetime import datetime

from pydantic import BaseModel


class BrokerStatus(BaseModel):
    broker: str
    mode: str  # "live" | "mock"
    last_sync_at: datetime | None
    healthy: bool
    warning: str | None


class DigestStatus(BaseModel):
    last_run_at: datetime | None
    last_status: str | None  # "sent" | "fallback_sent" | "failed" | None (never run)
    last_error: str | None


class StatusOut(BaseModel):
    brokers: list[BrokerStatus]
    digest: DigestStatus


class BrokerSyncResult(BaseModel):
    ok: bool
    count: int | None = None
    pruned: int = 0
    error: str | None = None


class RefreshOut(BaseModel):
    results: dict[str, BrokerSyncResult]
