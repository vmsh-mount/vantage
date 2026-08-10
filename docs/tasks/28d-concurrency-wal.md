# 28d — Concurrency & SQLite WAL

**Depends on:** 28c (multi-turn + WebSocket bridge — this is what makes "a scheduled job and a
live panel session both touching SQLite at once" a real scenario, not a hypothetical)
**Unlocks:** 29 (the panel can now safely run while the scheduler's sync tick / task 27's digest
also run, without either corrupting or blocking the other)

## Goal

A scheduled job (task 5's sync tick, task 27's digest) and a live panel session (task 28c's WS
endpoint, spawning `claude` subprocesses that call task 26's MCP tools) must be able to touch the
same SQLite file **at the same time** without either erroring with "database is locked" or
silently corrupting data. Also: a `claude` subprocess dying mid-turn (crash, kill, OOM) must not
leave the DB in a bad state or wedge bridge-server.

## Scope

**Design, chosen deliberately over a hand-rolled app-level write lock:** SQLite's own documented
mechanism for this exact problem is **WAL journal mode + `busy_timeout`** — WAL lets readers
proceed without blocking on a writer (and vice versa), and `busy_timeout` makes a second writer
that arrives while another write is in flight **retry internally for N ms** instead of
immediately raising `OperationalError: database is locked`. This is the standard recipe, not a
guess — and it fits this project's actual write patterns: every write path except the sync
pipeline (task 5, task 12's `_sync_lock` already serializes its two callers) is a single-row
upsert taking well under a second (task 26's `set_threshold`, task 27's `DigestLog` row). A busy
window of a few seconds comfortably covers real contention without needing a new global
app-level lock for every writer — `_sync_lock` already exists for the one write path that's
actually slow enough to matter as a lock target.

**`bridge-server/app/db.py`** (modified):
- A SQLAlchemy `event.listens_for(engine, "connect")` handler runs `PRAGMA journal_mode=WAL` and
  `PRAGMA busy_timeout=<ms>` on every new raw connection (WAL is persisted in the file once set,
  but asserting it on every connect is cheap and self-healing if the file was ever created
  without it).
- New setting `sqlite_busy_timeout_ms` in `app/config.py` (default 5000).

**Two honest findings from testing this directly, not glossed over:**
- **Python's own `sqlite3.connect()` already defaults to `timeout=5.0`** (confirmed via
  `help(sqlite3.connect)`) — SQLAlchemy's sqlite dialect uses this driver underneath, so
  write/write serialization existed *before* this task's explicit `PRAGMA busy_timeout`, as an
  implicit library default. The explicit PRAGMA is still worth keeping — it makes the intent
  documented and tunable via `settings.sqlite_busy_timeout_ms` rather than resting on an unstated
  driver default that could differ if the connection setup ever changes — but it's honest to say
  it's not the sole reason concurrent writes were surviving in ad hoc testing before this task.
- **A synthetic test designed to show WAL blocking fewer reads than rollback-journal mode came
  back inconclusive** (0.00s reader wait in *both* modes). Root cause: a writer only blocks
  readers during the brief moment it actually commits (RESERVED → PENDING → EXCLUSIVE), not for
  the whole time it holds a transaction open — and the test's artificial delay was placed *before*
  commit, entirely inside the window where concurrent reads are already allowed under either
  journal mode. Rather than force a misleading "WAL wins by Xs" number from a test that didn't
  land in the right window, this is recorded as genuinely unproven by this task's own testing —
  WAL is kept anyway because it's SQLite's own documented recipe for this scenario and the
  concurrent-writer test below (the one that actually matters for this task's real requirement)
  passes cleanly with it enabled.

**Mid-tool-call crash handling** — verified, and mostly *already* correct by construction from
earlier tasks rather than needing new mechanism:
- Task 26's MCP tools each open their own `SessionLocal()`, do their work, and commit within one
  request-response cycle **entirely server-side** — a `claude` subprocess dying after sending a
  tool call but before receiving the response cannot leave a half-written transaction, because
  the transaction's fate was already decided server-side independent of whether the client is
  still alive to hear about it.
- Task 28a's `run_one_shot` already reaps the subprocess with a timeout + kill fallback in its
  `finally` block, and already raises `AgentRunError` (not a hang) if the process ends without a
  terminal `result` event — exactly what a mid-turn crash produces. Task 28c's WS handler already
  catches `AgentRunError` per-turn and keeps the connection alive for the next prompt.
- This task's job is to **prove that chain holds under a real kill**, not re-architect it — see
  Acceptance criteria.

## Out of scope

- No app-level global write lock beyond `_sync_lock` (already existed, task 12) — see the Scope
  reasoning above for why WAL + `busy_timeout` is the mechanism, not a new lock.
- No change to how task 26's MCP tools manage sessions — already correct (verified here, not
  rebuilt).
- No retry/resume logic for a turn that failed mid-crash — task 28c's WS handler already reports
  the error and lets the next prompt start fresh; building automatic retry is a task 29 UX call,
  not this task's.

## Acceptance criteria

- `PRAGMA journal_mode` reads back as `wal` and `PRAGMA busy_timeout` reads back as the
  configured value on a real connection — confirmed by querying them, not just asserting the
  `PRAGMA` statements were issued. **Verified**: `journal_mode=wal`, `busy_timeout=5000`.
- **Real concurrent-writer stress test**: a long-running write transaction (simulating the sync
  pipeline's multi-row write) and a fast concurrent write (simulating a live `set_threshold` MCP
  call) are fired to genuinely overlap in time (not sequentially) — both succeed, no "database is
  locked" error, and both writes are independently confirmed durable afterward. **Verified**: a
  writer holding the write lock open for 2s and a second writer starting 0.5s later both
  succeeded; the second writer's commit visibly took 1.60s (waiting out most of the remaining
  lock-hold time via `busy_timeout`, not failing immediately), and both rows were confirmed
  present afterward.
- **Real mid-tool-call crash test**: a real `claude` subprocess spawned via `run_one_shot` is
  forcibly killed (`SIGKILL`) while mid-turn — `run_one_shot` surfaces a clean `AgentRunError`
  (not a hang, not an unhandled exception), the DB has no partial/orphaned state from whatever
  ran before the kill, and a **new** turn immediately afterward (fresh `run_one_shot` call, same
  process bridge-server is running in) succeeds normally — confirming the crash didn't wedge
  anything at the bridge-server level. **Verified**: `SIGKILL` on a real subprocess mid-generation
  produced `AgentRunError: claude exited (code -9) without a terminal result event`; an
  immediately-following fresh turn completed normally.
- The existing `_sync_lock`-guarded sync pipeline and a concurrent live panel turn are run
  together for real (not simulated separately) and both complete correctly. **Verified with the
  actual production functions**, not a simulation: `scheduler.run_sync_pipeline()` (real function,
  real threading) run concurrently with a real `run_one_shot` agent turn calling `set_threshold`.
  Both completed successfully — the sync pipeline's own broker calls hit real `401 Unauthorized`
  responses (today's known daily PaytmMoney/INDmoney token reset, unrelated to this task and
  already handled by task 5's existing error path), but it still completed its DB work
  (snapshots, `ApiCallLog` rows) without blocking or being blocked by the concurrent agent write —
  the threshold row was independently confirmed written to the DB afterward.
