# 05 — Scheduler & Sync Pipeline

**Depends on:** 02, 03
**Unlocks:** 06, 07, 08, 09, 12 (every read API depends on this having run at least once)

## Goal

The job that actually keeps the local DB in sync with both brokers — the thing that
makes this a "consolidated dashboard" instead of a one-off script.

## Scope

`bridge-server/app/scheduler.py` — APScheduler `BackgroundScheduler`, started from `main.py`'s
startup hook (task 1), interval job every `REFRESH_INTERVAL_MINUTES` (default 20). Each
tick:
1. Calls every broker client currently active (live or mock), from task 3.
2. Normalizes results to `NormalizedHolding`.
3. Upserts into `Holding` (matched by broker+symbol) — manual/CSV holdings
   (`source='manual'`) are never touched by this job.
4. Appends one `PortfolioSnapshot` row (aggregated across *all* holdings, including
   manual ones) and one `HoldingSnapshot` row per holding.
5. Writes an `ApiCallLog` row per broker call, including failures — failures are
   logged, not swallowed.

Also in scope: a synchronous version of the same pipeline, callable directly, for task
12's `POST /api/refresh` to reuse rather than duplicate.

## Out of scope

- No routers/endpoints yet — this task only produces correctly-populated tables.
- No token-expiry UI messaging — that's task 12's `/api/status`; this task's job is
  just to log the failure honestly when a token is rejected.

## Acceptance criteria

- With `PAYTMMONEY_MODE=live`, `INDMONEY_MODE=mock`: after one tick, `Holding` contains
  real PaytmMoney rows plus mock INDmoney rows, `PortfolioSnapshot` has exactly one new
  row, `HoldingSnapshot` has one new row per holding, `ApiCallLog` has one row per
  broker call.
- Manually edit a `source='manual'` holding, run a tick, confirm it's untouched.
- Temporarily break the PaytmMoney token, run a tick, confirm the failure is logged
  (not thrown/crashed) and mock/other data still syncs normally.
