# 35 — Memory-Poisoning Defenses

**Depends on:** 33, 34 (something has to exist to tag)
**Unlocks:** 36 (the desk note should read quarantine-aware, from day one)

## Goal

Planning-phase2.md §7's explicit concern: *"Memory-poisoning is a durable write, not a rejectable
suggestion. If memory is read on every run, one poisoned run biases all subsequent output."* Once
`Thesis`/`DecisionLog` rows get read back into future panel context (task 36 especially), a run
that ingested manipulated web content (invariant #3's live threat, already adversarially tested in
task 28e) could write a poisoned thesis entry or decision log that quietly shapes every later
answer. This task adds the provenance + quarantine layer before that reading-back happens for
real.

## Scope

**Real decision — quarantine lifts only by explicit user action, never automatically.** An
auto-lift rule (e.g. "trusted again after N days with no complaint") would be a rule an attacker
could simply wait out — the same class of mistake invariant #2's original "three enforcement
layers" review already corrected once elsewhere in this plan. Quarantine is binary and sticky
until a human looks at it.

**`bridge-server/app/models/thesis.py`, `decision_log.py`** (modified) — both tables get:
```python
run_session_id: Mapped[str]              # the claude session_id that produced this row
touched_untrusted_content: Mapped[bool] = mapped_column(default=False)
reviewed: Mapped[bool] = mapped_column(default=False)  # only True via explicit review
```

**`bridge-server/app/agent_security.py`** (modified) — `build_scoped_extra_args`'s
`enable_web=True` path already exists (task 28e); this task adds a way for the *writing* tool
call (`add_thesis_entry`/`log_decision`) to know, at write time, whether **this same session**
ever called `WebFetch`/`WebSearch` earlier in the conversation. Simplest correct mechanism: the
WS handler (task 28c's `agent_ws.py`) already sees every event streaming past, including every
`tool_use` — it already tracks `session_id`; it now also tracks a per-connection
`touched_untrusted_content` flag, set `True` the first time a `WebFetch`/`WebSearch` `tool_use`
event is seen, and passes both down whenever it forwards a write-tool call's *result* is
irrelevant — what matters is tagging the row `log_decision`/`add_thesis_entry` themselves create,
which happens inside the same MCP call the WS loop already observes. Concretely: `vantage_mcp.py`
tools can't see WS-layer state directly (different process boundary — MCP tools run inside
bridge-server's own request handling, not the WS loop), so the tag is set via a small
per-`run_one_shot`-call context: `agent_ws.py` passes `session_id` and a running
`touched_untrusted_content` boolean into a `contextvars.ContextVar` before each turn; the write
tools read it when constructing the row. Verified live, not assumed — see Acceptance criteria.

**`get_thesis_history`/decision-log read tools** (modified) — filter out
`touched_untrusted_content=True AND reviewed=False` rows from what's returned by default, so a
quarantined write can't shape a future run's context. A `include_quarantined=True` parameter
exists for explicit review, not for routine reads.

**`bridge-server/app/routers/quarantine.py`** (new) — `GET /api/quarantine`,
`POST /api/quarantine/{table}/{id}/review`. No new frontend page for this — a small section added
to the existing Status page (task 12/18) is enough surface for something that should be rare, not
a whole new UI investment for a hopefully-empty list.

## Out of scope

- No automatic "this content looks suspicious" classifier — the flag is purely "did this session
  call WebFetch/WebSearch at all," a coarse but honest signal, not an attempt to distinguish
  malicious from benign fetched content (task 28e's adversarial testing already showed the model
  itself resists injection well; this is defense-in-depth on top of that, not a replacement).
- No retroactive tagging of `Thesis`/`DecisionLog` rows written before this task ships — tasks 33
  and 34 don't exist yet at the time this is written, so there's nothing to retrofit.
- No automated review/approval logic — a human looks, or it stays quarantined indefinitely.

## Acceptance criteria

- A real panel session that calls `WebSearch` and then `log_decision` in the same conversation
  produces a `DecisionLog` row with `touched_untrusted_content: true` — verified live, not
  inferred from code reading alone, since the context-passing mechanism above is genuinely new
  plumbing (task 28c's WS loop hasn't needed to pass anything into a tool call before this).
- A session that never calls a web tool produces `touched_untrusted_content: false` — the flag
  doesn't default to true or leak across separate WS connections (same isolation task 28c's own
  "two independent connections don't share context" check already verified for conversation
  history; this re-verifies it for the new flag specifically).
- `get_thesis_history` (or the decision-log equivalent) omits an unreviewed quarantined row by
  default, and includes it when `include_quarantined=True` — verified both ways in the same test.
- `POST /api/quarantine/{table}/{id}/review` flips `reviewed` and the row becomes visible in the
  default read again — confirmed via a real before/after read, not just the write succeeding.

**Verified live, 2026-08-10 — two real bugs found and fixed along the way**, not just a clean
first pass (see app/run_context.py's own docstring for the full technical trace):

1. **BaseHTTPMiddleware doesn't propagate contextvars into the wrapped app.** The first
   implementation used Starlette's `BaseHTTPMiddleware`. A real WS session calling `WebSearch`
   then `log_decision` showed the middleware's own instrumentation correctly saw
   `touched=True` for the `log_decision` request, yet the persisted row still came back
   `touched_untrusted_content: false`. Root cause: `BaseHTTPMiddleware.dispatch` runs the
   downstream ASGI app via an internal `anyio` task group — a documented Starlette gotcha where
   contextvars set in `dispatch` don't reliably reach the wrapped app's own task. Fixed by
   rewriting `RunContextMiddleware` as a plain ASGI middleware (`__call__(self, scope, receive,
   send)`, no task group).
2. **A genuine same-turn race**, not a bug in this module: when the model calls `WebSearch` and
   `log_decision` as two tool_use blocks in the *same* assistant turn (the `claude` CLI dispatches
   them essentially in parallel), the loopback HTTP call for `log_decision` can beat
   agent_ws.py's own stdout-read loop to registering the web-tool flag — confirmed by instrumenting
   both sides with real timestamps. Fixed with `reconcile_touched_rows`: after every turn finishes
   (by which point the connection's touched state is fully known), it retroactively flips
   `touched_untrusted_content` on any row *that turn* wrote and lost the race — scoped by
   `created_at >= turn_start` so an earlier turn's already-settled clean rows are never touched.

After both fixes, re-ran the exact same-turn test against the real running bridge-server (`mcp` SDK
`ClientSession` triggered via a real `websockets` connection to `/ws/agent`, not a mock): the
`DecisionLog` and `Thesis` rows both correctly persisted `touched_untrusted_content: true`. A
parallel clean-session test (explicitly no web tool call) correctly persisted `false`, on a
different WS connection with its own `run_key` — confirming no cross-connection leakage. Quarantine
filtering verified both directions (`get_decisions`/`get_thesis_history` omit the row by default,
include it with `include_quarantined=True`), and `POST /api/quarantine/{table}/{id}/review` verified
via a real REST round-trip that flips `reviewed` and restores default visibility — confirmed both
via direct API calls and, for the frontend Status-page addition, via a real click through the
Browser tool (`Mark reviewed` → real `POST /api/quarantine/theses/1/review` → 200 → the row
disappears and "Nothing quarantined." renders). All test rows deleted afterward — no residue in the
real local DB.
