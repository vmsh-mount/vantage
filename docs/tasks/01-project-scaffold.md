# 01 — Project Scaffold & Config

**Depends on:** —
**Unlocks:** everything else

## Goal

A running FastAPI app with nothing in it yet — config loading, DB connection, and a
health check. The foundation every other task builds on.

## Scope

- `bridge-server/app/main.py` — FastAPI app instance, CORS (open to the Vite dev origin only),
  a startup hook (scheduler wiring comes later, in task 5 — for now just a no-op or a
  `GET /api/health`).
- `bridge-server/app/config.py` — pydantic-settings class loading `.env`: broker keys/secrets/
  tokens, `PAYTMMONEY_MODE` / `INDMONEY_MODE`, `REFRESH_INTERVAL_MINUTES`,
  `FX_MANUAL_RATE`.
- `bridge-server/app/db.py` — SQLAlchemy engine + session factory against a local SQLite file,
  plus an init function that creates tables on startup (no migration tool for a
  single-user local app — schema changes during development just mean deleting the
  SQLite file).
- `bridge-server/requirements.txt` — fastapi, uvicorn, sqlalchemy, apscheduler, httpx,
  pydantic-settings.
- `bridge-server/.env.example` — every variable from `config.py`, documented inline, no real
  values.
- `.gitignore` — `.env`, `*.db`, `__pycache__/`, `node_modules/`, `dist/`.

## Out of scope

- No models yet (task 2).
- No routers yet — `/api/health` is the only endpoint.
- No scheduler logic yet (task 5) — just confirm the startup hook fires.

## Acceptance criteria

- `uvicorn app.main:app --reload` starts cleanly with no `.env` values filled in beyond
  placeholders (mock-safe defaults).
- `GET /api/health` returns `200`.
- Missing/malformed `.env` values fail fast with a clear pydantic validation error, not
  a silent default or a crash three layers down.
