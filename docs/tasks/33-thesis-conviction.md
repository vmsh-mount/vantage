# 33 — Thesis + Conviction (Versioned, Historized)

**Depends on:** 29 (the panel — this task's only real consumer, at least at first)
**Unlocks:** 34 (`decision_log` FKs into `thesis`), 36 (the desk note reasons over thesis history)

## Goal

Half B's foundational piece (planning-phase2.md §7): a real investment-thesis record per holding
that's append-only (scale-ins and evolving views are representable, unlike a single mutable row)
with a timestamped conviction score (so calibration over time is actually checkable, unlike an
untimestamped score that freezes at whatever was first typed).

## Scope

**Real decision — coexists with task 32's `Holding.notes`, doesn't replace it.** The plan frames
task 32 explicitly as the cheap, always-visible tier of this same idea ("the kept-cheap piece of
Half B") and this as the "expensive apparatus" — deliberately two different weights, not one
being an upgrade path for the other. `Holding.notes` stays the quick one-liner shown right on the
Dashboard row. `Thesis` is the fuller, versioned history for when a one-liner genuinely isn't
enough — e.g. "why I'm still holding this after it dropped 18%" deserves more than overwriting a
single field. A future UI pass could surface `Thesis` entries alongside `notes` on the same row;
not required for this task to be useful on its own.

**Real decision — agent-only, no new frontend page.** Consistent with Half A's whole
"no journaling ritual" reframe: this ships as two new Vantage MCP tools
(`app/vantage_mcp.py`) — `add_thesis_entry` and `get_thesis_history` — so you write a thesis by
telling the panel ("log my thesis on SWIGGY: bought after the delivery-volume beat, holding
through FY27") rather than filling out a form. If it turns out a dedicated UI is actually wanted
once this gets used, that's a real, separate follow-up call to make later — not assumed here.

**`bridge-server/app/models/thesis.py`** (new):
```python
class Thesis(Base):
    __tablename__ = "theses"
    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str]
    symbol: Mapped[str]
    text: Mapped[str]
    conviction: Mapped[int | None]  # 1-5, nullable — not every entry states one
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```
Append-only by construction: no `PUT`/`PATCH` endpoint or MCP tool exists for this table, only
insert. "Current" thesis for a holding = the latest row for that (broker, symbol) — a query, not
a separate mutable field, so there's no risk of the "current" pointer and the history disagreeing.

**`bridge-server/app/vantage_mcp.py`** (modified):
- `add_thesis_entry(broker, symbol, text, conviction=None)` — insert-only, task 26's write-tool
  pattern (opt-in via `agent_security.py`, same as `set_threshold`).
- `get_thesis_history(broker, symbol)` — read tool, returns every entry oldest-first so the
  agent can see the view evolving, not just the latest snapshot.

## Out of scope

- No dedicated frontend UI (see Scope above) — agent-only for this task.
- No retrofit of task 32's `Holding.notes` into this table, and no UI change to the existing
  notes input — genuinely separate, coexisting features.
- No automatic thesis generation (e.g. the agent proactively writing one unprompted) — every
  entry is an explicit, user-directed write via the panel.
- No conviction-calibration reporting (e.g. "your high-conviction calls do better than your
  low-conviction ones") — that's a real analysis to build once there's enough real history to
  analyze, not before.

## Acceptance criteria

- A real thesis entry, added through the panel via `add_thesis_entry`, persists and is returned
  correctly (oldest-first, with `conviction` when given) by `get_thesis_history` — verified with a
  real MCP tool call round-trip, not just a schema check.
- Adding a second entry for the same holding never overwrites or deletes the first — both remain
  queryable, confirming append-only actually holds under real use, not just by the absence of an
  UPDATE endpoint.
- `Holding.notes` is unaffected by any Thesis activity on the same holding — confirmed independent
  read/write, same rigor as task 32's own equivalent check against `Threshold.notes`.

**Verified live, 2026-08-09.** Against the real running bridge-server (not a test double), via an
actual `mcp` SDK `ClientSession` over `streamable_http` — the same transport the panel itself uses,
not a direct Python function call:
- `add_thesis_entry` called twice for the same (broker, symbol) → both rows persisted with distinct
  `id`/`created_at`; `get_thesis_history` returned both, oldest-first, second entry did not
  overwrite the first.
- Set a real holding's (`SWIGGY`) `notes` to a marker value, called `add_thesis_entry` for the same
  symbol via the live MCP endpoint, re-read the holding — `notes` unchanged, confirming the two
  tables don't interact.
- Test rows deleted afterward; `SWIGGY.notes` reverted to its prior value (`None`) — no residue left
  in the real local DB.
