# 02 — Data Models

**Depends on:** 01
**Unlocks:** everything that reads or writes the DB

## Goal

Every table from architecture.md's Data Model section, as SQLAlchemy models plus their
Pydantic read/write schemas — no business logic yet, just the shape of the data.

## Scope

`bridge-server/app/models/` (SQLAlchemy, one file per table, `__init__.py` re-exports
all six so `from app.models import Holding` keeps working everywhere else):
- `Holding` — current state, upserted on refresh (broker+symbol unique). Includes
  `close_price` (previous day's close) as a **nullable** field — unconfirmed whether
  either broker actually returns it (see planning.md Gaps); today's-move must be able
  to fall back to a snapshot-delta calculation when it's null (task 6 owns that logic,
  this task just makes sure the column allows null).
- `PortfolioSnapshot` — one row per scheduler tick: `captured_at`,
  `total_net_worth_inr`, `breakdown_json`.
- `HoldingSnapshot` — one row per holding per tick: `captured_at`, `broker`, `symbol`,
  `market_value_inr`, `ltp`, `pnl_pct`.
- `RiskSettings` — single-row table: `concentration_stock_pct` (default 15),
  `concentration_sector_pct` (default 30), `target_india_pct`, `target_us_pct`
  (nullable — no target until the user sets one).
- `Threshold` — broker+symbol → `stop_loss_pct`, `target_pct`, `notes`. Sign
  convention: `stop_loss_pct` negative, `target_pct` positive (matches
  architecture.md's Threshold row) — worth a validation check on write (task 11) that
  rejects a positive stop-loss or negative target as a likely input mistake.
- `ApiCallLog` — `broker`, `endpoint`, `status_code`, `called_at`.

`bridge-server/app/schemas/` (Pydantic, one file per resource, mirrors `models/`):
- Read/write schemas for each model above, matching what the routers in later tasks
  will actually need (e.g. `HoldingOut`, `ThresholdIn`/`ThresholdOut`,
  `RiskSettingsIn`/`Out`).

DB init (extends task 1's `db.py`): create all tables on startup; seed a single default
`RiskSettings` row if none exists (15 / 30 / null / null).

## Out of scope

- No CRUD endpoints yet (later tasks own their own routers).
- No migrations — schema changes during development mean deleting the SQLite file, per
  task 1.

## Acceptance criteria

- Fresh DB file, on startup, contains all six tables plus exactly one `RiskSettings`
  row with the documented defaults.
- Every field listed in architecture.md's Data Model section exists on the
  corresponding model — this task is the source of truth check against that doc.
