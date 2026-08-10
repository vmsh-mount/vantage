# 32 — Holding Notes

**Depends on:** — (independent of everything, per planning-phase2.md §6.1's own note)
**Unlocks:** 29 (the panel reads these notes so the agent can reason about *why* you own something)

## Goal

A zero-ceremony free-text "why I own this" note per holding (planning-phase2.md §7): one nullable
column, one input on the holdings row. No structured invalidation conditions, no horizon fields,
no re-scoring ritual — just a place to jot a reason that quietly accumulates for task 29's panel
to read later.

## Scope

**Real decision made before writing code**: `Threshold` already has its own `notes` field
(task 2), but it's the wrong place for this — it's scoped to *why you set this stop-loss/target*,
a `Threshold` row only exists once you've actually set one, and deleting a threshold (`DELETE
/api/thresholds`) deletes that row entirely. Reusing it for "why I own this" would silently lose
the note the moment a threshold gets cleared, and conflates two different concerns the Thresholds
page's own copy ("Independent of any broker-side alerts — these thresholds are yours") already
treats as separate. This task adds a genuinely new `notes` column directly on `Holding`,
independent of whether a threshold exists at all — matching the plan's literal wording ("one
nullable column ... on the holdings row").

- **`bridge-server/app/models/holding.py`**: `notes: Mapped[str | None] = mapped_column(default=None)`.
- **`bridge-server/app/schemas/holding.py`, `app/schemas/dashboard.py`**: add `notes: str | None`
  to `HoldingOut` and `DashboardHolding`.
- **`bridge-server/app/routers/holdings.py`**: `PUT /api/holdings/{holding_id}/notes` — a small,
  dedicated endpoint, deliberately separate from the manual-only CRUD endpoints above it (those
  are scoped to `source == "manual"`; notes apply to any holding, API-sourced or manual).
- **`bridge-server/app/routers/dashboard.py`**: include `notes=h.notes` per holding row.
- **`deck-app/src/pages/Dashboard.tsx`**: one more column on the existing holdings table, same
  inline-input/blur-to-save pattern as the Thresholds page's stop-loss/target inputs — no new
  page, no modal, no expandable row.

## Out of scope

- No structured invalidation conditions, horizon fields, or re-scoring ritual — explicitly the
  "expensive, rot-prone apparatus" §7 defers, not this column.
- No retrofit of `Threshold.notes` — left as-is, still used for its own purpose.
- No consumer built here — task 29 reads these notes later; this task only makes them exist and
  be editable.

**Real migration issue found and fixed while verifying**: `Base.metadata.create_all()` only
creates missing *tables*, never adds columns to an existing one — and this project's local DB
already had real holdings in it from every prior task's testing. The first `/api/dashboard` call
after adding `Holding.notes` failed with `OperationalError: no such column: holdings.notes`. This
project has no migration tool for one column; fixed with a small self-healing check in
`init_db()` (`PRAGMA table_info` + `ALTER TABLE ... ADD COLUMN` if missing) rather than requiring
a manual one-off fix per checkout — the first case in this project of adding a column to a table
that already holds real data, not just a new table.

## Acceptance criteria

All verified against a real running bridge-server + a real browser session (Vite dev server,
`websockets`-free plain fetch calls), not just curl:

- A note set via the UI persists across a page reload and a bridge-server restart (real DB
  column, not client-only state). **Verified**: typed a note on SWIGGY through the actual
  Dashboard input, confirmed the `PUT` fired and returned 200, restarted bridge-server, reloaded
  the page, and independently confirmed via a direct API call that the note was still there.
- Setting a note on an API-sourced holding (not just a manual one) works — the endpoint isn't
  scoped to `source == "manual"` the way the existing CRUD endpoints are. **Verified**: SWIGGY
  (`source: "api"`, a real PaytmMoney holding) is exactly what was used above.
- Clearing a note (empty string) actually nulls the column, not just displays empty. **Verified**
  twice — once directly via the API (`{"notes": ""}` → `null`), and once through the real UI
  (after some browser-automation friction with click/selection timing unrelated to the app itself,
  resolved by setting the field's value directly and blurring) — confirmed `null` afterward via
  a fresh API read, not just "the input looked empty."
- `Threshold.notes` is unaffected by any of this — confirmed independent read/write. **Verified**:
  set a `Holding.notes` value on SWIGGY, checked `GET /api/thresholds` for SWIGGY in the same
  moment — `notes: null` there, untouched.
