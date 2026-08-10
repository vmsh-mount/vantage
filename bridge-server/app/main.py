from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.routers import (
    agent_ws,
    alerts,
    dashboard,
    decisions,
    facts,
    holdings,
    quarantine,
    risk,
    statements,
    status,
    tax,
    thresholds,
    trend,
)
from app.routers import settings as settings_router
from app.run_context import RunContextMiddleware
from app.scheduler import start_scheduler, stop_scheduler
from app.vantage_mcp import mcp as vantage_mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    # Mounting an ASGI sub-app doesn't make the parent invoke its lifespan —
    # Starlette only runs lifespan for the top-level scope, never for a
    # Mount()'d app. The session manager has to be entered here instead, or
    # every MCP request 500s with "Task group is not initialized."
    async with vantage_mcp.session_manager.run():
        yield
    stop_scheduler()


app = FastAPI(title="Vantage", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
# Task 35: wraps the mounted /mcp sub-app too (Starlette middleware applies
# across Mount() boundaries) — see app/run_context.py's docstring.
app.add_middleware(RunContextMiddleware)


app.include_router(dashboard.router)
app.include_router(risk.router)
app.include_router(alerts.router)
app.include_router(trend.router)
app.include_router(holdings.router)
app.include_router(thresholds.router)
app.include_router(settings_router.router)
app.include_router(status.router)
app.include_router(statements.router)
app.include_router(tax.router)
app.include_router(facts.router)
app.include_router(decisions.router)
app.include_router(quarantine.router)
app.include_router(agent_ws.router)

app.mount("/mcp", vantage_mcp.streamable_http_app())


@app.get("/api/health")
def health():
    return {"status": "ok"}
