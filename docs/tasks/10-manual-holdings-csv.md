# 10 — Manual Holdings & CSV Import

**Depends on:** 02
**Unlocks:** —

## Goal

The write path for US holdings, since INDmoney's API doesn't expose them (key decision
in planning.md — manual entry, not scraped).

## Scope

`bridge-server/app/routers/holdings.py`:
- `POST /api/holdings/manual` — create (`source='manual'`, `broker='indmoney'`,
  `currency='USD'`, `asset_class='us_equity'` implied).
- `PUT /api/holdings/manual/{id}` — edit.
- `DELETE /api/holdings/manual/{id}` — delete.
- `POST /api/holdings/manual/import-csv` — parses pasted/uploaded rows
  (`symbol, qty, avg_cost, sector` — one per line, per the format already documented in
  the UI prototype's Manual Holdings page) into multiple manual holdings in one call.

**Post-review fixes (2026-07-19):**
1. **`close_price` was being set to `ltp` on every create and edit** — directly
   contradicting the architecture.md Data Model row this same review pass had just
   corrected ("never present for manual holdings"). Harmless today only because every
   current reader checks `source == 'manual'` first (Trajectory, today's-move), but a
   live trap: `close_price` is exposed on `HoldingOut` directly, so any future code
   computing `ltp - close_price` without checking `source` first wouldn't get a
   visibly-missing `None` — it'd silently compute a fabricated "0% move today" instead.
   Fixed: manual holdings now always get `close_price = None`.
2. **Edit semantics for an omitted `ltp` needed an explicit decision.** `ManualHoldingIn`
   is shared by create and edit; on create, omitting `ltp` sensibly defaults to
   `avg_cost` (fresh baseline, nothing to preserve). On edit, the same fallback would
   silently reset a previously-tracked price back to cost basis as a side effect of an
   unrelated field change (e.g. a "just bumped my quantity" edit) — surprising, and a
   real risk once a "quick edit" UI exists in `deck-app` and doesn't always resend
   every field. Decided in favor of the safer default: **edit without `ltp` now
   preserves the holding's current price**; only an explicit `ltp` in the payload
   reprices it. Create behavior unaffected.

Both verified with a full regression pass (CRUD, CSV import, Trajectory/Alerts
integration) confirming nothing else broke.

## Out of scope

- No validation against a live symbol lookup (e.g. confirming AAPL is real) — trust the
  user's input, single-user local app.
- The scheduler (task 05) already guarantees it never touches `source='manual'` rows —
  this task doesn't need to re-enforce that, just rely on it.

## Acceptance criteria

- Create → appears in `GET /api/dashboard` on the next call (no scheduler tick needed —
  manual writes are immediately visible).
- Edit → market value recalculates using the new qty/avg_cost.
- Delete → disappears from the dashboard immediately.
- CSV import with a malformed line (missing a field) skips that line rather than
  failing the whole batch, and reports which lines were skipped.
- `close_price` is always `null` for a manual holding, on both create and edit — never
  silently populated from `ltp`.
- Editing a holding without providing `ltp` preserves its current price; only an
  explicit `ltp` in the request changes it.
