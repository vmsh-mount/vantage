# 28c — Multi-Turn + WebSocket Bridge

**Depends on:** 28b (security allowlist — every turn spawned here reuses `build_scoped_extra_args`)
**Unlocks:** 28d (concurrency/WAL — only a real risk once a live panel session, built here, can
run alongside the scheduler); 29 (the actual panel UI, deck-app's consumer of this endpoint)

## Goal

A live, multi-turn conversation between the browser and a real `claude` subprocess, bridged over
a WebSocket — the "genuinely new territory" planning-phase2.md §4 names (everything through task
27 is sync `def` on a threadpool; this is bridge-server's first async subprocess-to-WS code).

## Scope

**Real constraints discovered live before settling on a design:**

- The plan names two alternative multi-turn mechanisms: `--resume`/`--session-id` (spawn a fresh
  process per turn, continuing a saved session) or bidirectional `--input-format stream-json`
  (one long-lived process, messages streamed in over stdin). **Both were tested directly and both
  genuinely retain conversation context** — confirmed with the same probe against each
  (`"My favorite number is 77"` → later turn correctly answers `"77"`).
- **A methodology trap along the way, caught and corrected**: the first version of this probe used
  "remember the secret word is BANANA77" phrasing, and *both* mechanisms appeared to fail — the
  model responded "I don't retain information between conversations... I don't save secret words."
  That's a safety-flavored refusal pattern triggered by "secret word" framing, **not** a real
  absence of context — confirmed by rerunning the identical mechanism with neutral phrasing
  ("my favorite number is 77"), which worked cleanly both times. Recorded here so the false
  negative doesn't get rediscovered the hard way later.
- **Chose `--resume` (spawn-per-turn) over the persistent bidirectional process.** Both work; this
  one wins on fit for this project specifically: it reuses task 28a's `run_one_shot` almost
  verbatim (just appends `--resume <session_id>` once a session exists) rather than needing a new
  long-lived-subprocess registry with its own idle-timeout/cleanup/reconnect-to-existing-process
  logic. State lives in the session file `claude` itself manages on disk, not in bridge-server
  memory — a browser reconnect is just "resume the same session_id again," no process to find or
  keep alive. Matches this project's established preference for the simpler mechanism until the
  more complex one is *actually* needed (task 24's connect-per-call MCP client made the identical
  call for the identical reason).
- **A real, non-security cost found while testing `--resume` combined with task 28b's scoping**:
  with no `Write` tool available (28b), the model's own auto-memory habit (unrelated to Vantage —
  the same mechanism that writes to `~/.claude/.../memory/`) made it loop, calling `get_dashboard`
  five times while narrating "saving to memory now" between attempts, before finally giving up and
  answering in text. **Confirmed via the full event trace this was never a security gap** — `Write`
  isn't a real tool name in this session at all, so the model could only narrate wanting it, never
  actually call it — but it's a real wasted-turns/cost problem. `--bare` mode disables auto-memory
  but was tested and **breaks OAuth/subscription auth outright** ("Not logged in · Please run
  /login"), directly conflicting with this project's own "no API metering" principle
  (planning-phase2.md §1) — ruled out. Fixed with a targeted `--append-system-prompt` instead,
  added to `agent_security.build_scoped_extra_args` (not this task's own module, since it's a
  universal fix, not multi-turn-specific) — confirmed live this drops the tool-call count for the
  same prompt from 5 to 1.

**`bridge-server/app/routers/agent_ws.py`** (new) — `WebSocket` endpoint `/ws/agent`:
- Accepts a connection, then loops: receive a JSON message `{"prompt": "..."}` from the browser,
  call `run_one_shot(prompt, extra_args=build_scoped_extra_args() + (["--resume", session_id] if
  session_id else []))`, forward every yielded event to the browser as its own WS JSON frame **as
  it arrives** (not batched), capture `session_id` from the first turn's `system`/`init` event and
  reuse it on every subsequent turn on this connection.
- **Backpressure**: each event is sent with its own `await websocket.send_json(event)` inside the
  `async for` loop over `run_one_shot`'s generator — there's no intermediate buffer collecting
  events before sending, so if the browser can't keep up, the `await` naturally blocks the forward
  loop (and therefore the next read from the subprocess's stdout) rather than piling events up in
  memory. Verified live with a deliberately slow-reading test client (see Acceptance criteria).
- A disconnect (`WebSocketDisconnect`) simply ends the loop — no in-flight subprocess to clean up
  mid-turn here, since each turn is a bounded `run_one_shot` call that either finishes or the
  disconnect happens between turns. (A disconnect genuinely *mid-turn* still lets that turn's
  subprocess run to completion in the background before the next `receive_json` would occur, since
  nothing is listening for it — acceptable for this task; tightening that is 28d's "mid-tool-call
  crash handling" territory if it turns out to matter.)

## Out of scope

- No concurrency/WAL handling with the scheduler's own DB writes (28d) — this task doesn't change
  how bridge-server talks to SQLite at all; `run_one_shot`/MCP tool calls already go through the
  same `SessionLocal()` pattern every other task uses.
- No reconnect-with-history-replay UI affordance — task 29's concern, not this transport layer's.
- No token-by-token partial-message streaming (`--include-partial-messages`) — each turn's events
  stream live already (assistant messages, tool calls, tool results all arrive as they happen);
  sub-message token streaming is a UX polish call for task 29 to make, not required for the
  transport to be genuinely "live."
- The persistent-bidirectional-process alternative isn't built at all, not even partially — it was
  a real, working alternative (see Scope above), not a broken path kept as a fallback.

## Acceptance criteria

All verified with a real `websockets` client against a live bridge-server (`scripts/
agent_ws_smoke_test.py`), real `claude` subprocesses underneath, no mocks:

- A real multi-turn conversation over a real WebSocket client retains context across turns —
  verified with the neutral-phrasing probe (not the misleading "secret word" one). **Verified**:
  turn 2 correctly answered "77" to "what number did I just tell you."
- Every event from a turn arrives at the WS client individually, in order, matching what
  `run_one_shot` itself yields for the same prompt — not re-batched or altered in transit.
  **Verified**: `['system', 'rate_limit_event', 'assistant', 'system', 'result']`, same shape as
  every other task's direct `run_one_shot` observations.
- Backpressure is real, not assumed: a WS client that deliberately reads slowly measurably slows
  the server-side forward loop (observed via timing), rather than the server building an unbounded
  in-memory queue of unsent events. **Verified**: a 0.4s/event slow reader produced 3.0s of wall
  time for 5 events — consistent with the server pacing to the reader, not dumping a buffer
  instantly.
- The security scoping from 28b still holds across multiple turns on one WS connection — verified
  by attempting `set_threshold` (not allowlisted) mid-conversation and confirming denial, the same
  way 28b's own smoke test confirmed it for a single turn. **Verified directly against the
  `Threshold` table** (28b's own fix applied here too — not the holdings-joined `/api/thresholds`
  view, which would pass vacuously for a synthetic test symbol).
- A second, independent WS connection gets its own independent session — turns on one connection
  never leak into another's context. **Verified**: a second connection asked about "favorite
  color" (set on the first connection) and correctly showed no knowledge of it.
