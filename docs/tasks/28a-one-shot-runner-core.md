# 28a — One-Shot Claude Code Runner Core

**Depends on:** 26 (Vantage MCP server — not consumed yet, but this is the layer that will
eventually launch `claude` pointed at it)
**Unlocks:** 28b (security allowlist), which wraps this runner rather than replacing it

## Goal

Prove bridge-server can reliably launch a real `claude` CLI subprocess in one-shot mode, stream
its `stream-json` output as it arrives, and parse it into structured Python events — including
the cases naive line-reading gets wrong. No WebSocket, no MCP tool wiring, no permission
allowlist yet (planning-phase2.md §6.1: those are 28c/28b/28d/28e). This task is purely: **can
bridge-server run `claude` and get back reliable structured events, forever, without surprises.**

## Scope

**Real constraints discovered live before writing any code** (this machine's `claude` CLI,
version **2.1.121**, pinned below):

- `--output-format stream-json` **requires `--verbose`** when combined with `-p`/`--print` — the
  CLI refuses to start without it (`Error: When using --print, --output-format=stream-json
  requires --verbose`). Not documented as a hard requirement in `--help`'s per-flag text; only
  discovered by actually running it.
- Real event stream shape for a one-shot run (`claude -p "..." --output-format stream-json
  --verbose`), confirmed live: one JSON object per line —
  `{"type":"system","subtype":"init",...}` (session_id, tools, model, cwd, mcp_servers),
  `{"type":"assistant","message":{...}}` for each assistant turn, occasionally
  `{"type":"rate_limit_event",...}`, `{"type":"system","subtype":"post_turn_summary",...}`, and
  always a terminal `{"type":"result","subtype":"success"|...,"is_error":bool,"result":"...",
  "total_cost_usd":...,"session_id":...}` line — the one to actually stop reading on, not EOF,
  since EOF can lag the terminal event slightly depending on process teardown timing.
  **`system`/`init` is not reliably the first event** — confirmed live via the smoke test: a
  `rate_limit_event` (a separate async usage-check racing session init) arrived *before* it on
  one real run. Anything consuming this stream should search for `init`, not assume position 0.
- A prompt asking for "40000 repeated digits" produced a **383,510-character** response, not
  ~40,000 — the model substantially overshot the literal instruction. Harmless for this task
  (it made an even better stress test than planned for the >64KB-single-line case), but a real
  data point: don't trust a prompt's requested output size as an upper bound when sizing
  anything downstream that consumes runner output.
- **A single NDJSON line can exceed 64KB** — confirmed live by forcing a long single-turn
  response; `asyncio.StreamReader.readline()`'s default 64KB limit would either raise
  `LimitOverrunError` or silently hand back a truncated, unparseable line. This is exactly the
  "partial-JSON handling" the plan names — solved with manual chunked buffering
  (`stdout.read(n)` in a loop, splitting accumulated bytes on `\n`), not `readline()`, so there's
  no arbitrary line-length ceiling baked in silently.

**`bridge-server/app/agent_runner.py`** (new):
- `CLAUDE_CLI_VERSION_PINNED = "2.1.121"` — the version this runner is validated against.
- `async def run_one_shot(prompt, *, model=None, cwd=None, extra_args=None) -> AsyncIterator[dict]`
  — spawns `claude -p <prompt> --output-format stream-json --verbose [--model ...] [extra_args]`
  via `asyncio.create_subprocess_exec`, yields one parsed dict per NDJSON line as it arrives
  (not batched at the end — genuinely streamed), stops after the terminal `result` event, then
  awaits process exit and raises a clear error (including captured stderr) on a nonzero exit code
  that didn't already surface as a `result` event with `is_error: true`.
- `async def check_claude_cli_version() -> None` — runs `claude --version`, compares against the
  pin, logs a **loud warning** (not a silent pass-through) on drift rather than assuming
  compatibility. Doesn't hard-fail the runner on drift — a version bump upstream shouldn't brick
  bridge-server outright — but it must be impossible to miss in the logs.
- `extra_args` exists specifically so 28b can pass `--permission-mode`/`--allowedTools`/
  `--disallowedTools` through this same runner rather than needing a second one — this task
  doesn't use it, but the seam is deliberate.

**`bridge-server/scripts/agent_runner_smoke_test.py`** (new) — runs a real one-shot prompt against
the actual installed `claude` CLI (not a fixture) and asserts: the first event is `system`/`init`
with a `session_id`, the stream produces at least one `assistant` event, the terminal event is
`type == "result"`, and a version-drift check runs and reports pass/fail explicitly. Mirrors task
24's INDmoney contract smoke-test in spirit — this is the same "vendor interface I don't control
can drift silently" risk, just for the `claude` CLI instead of an MCP server.

## Out of scope

- No WebSocket, no browser-facing anything (28c).
- No permission-mode/allowlist enforcement — `extra_args` is a pass-through seam for 28b to use,
  not an enforcement point built here. Nothing in this task should be read as "the security
  boundary" — it isn't one yet.
- No multi-turn/`--resume`/`--session-id` (28c) — one-shot only.
- No concurrency/WAL handling (28d) — this task doesn't touch the DB at all.
- No MCP tool wiring — the runner doesn't yet point `claude` at task 26's Vantage MCP server or
  restrict its tool set in any way. A bare `run_one_shot` today gets whatever tools the host
  `claude` CLI's default config exposes, same as running `claude -p` by hand — genuinely
  unscoped, and the task doc says so rather than implying otherwise.

## Acceptance criteria

- A real one-shot prompt run through `run_one_shot` yields parsed events matching the live shape
  documented above — not asserted from reading `--help`, actually run. **Verified.**
- A prompt engineered to produce a >64KB single NDJSON line is parsed correctly — proven with a
  real long-response prompt, not a synthetic in-memory string. **Verified**: a 383,285-character
  response (the model substantially overshot the requested "40000 digits," a real data point
  noted above) parsed with zero truncation or corruption.
- **Revised after real testing** — the original wording here ("an invalid `--model` value...
  surfaces a clear Python exception") was an assumption written before running it, and turned out
  wrong: confirmed live, an invalid `--model` does **not** crash the process — the CLI emits a
  normal terminal `result` event with `is_error: true` and a real `api_error_status` (404 seen
  live). That's `run_one_shot`'s documented contract working exactly as intended (structured
  errors are yielded, not raised), not a gap. The acceptance criterion that actually needed
  checking — **does `AgentRunError` fire on a genuinely broken invocation** — was verified
  separately with an unsupported CLI flag (`--this-flag-does-not-exist`): the process exited
  nonzero with no NDJSON output at all, and `AgentRunError` fired with the real stderr
  (`error: unknown option '--this-flag-does-not-exist'`) attached. Both cases are now permanent
  smoke-test checks (`check_invalid_model_is_structured_error`, `check_bad_args_raises`).
- `check_claude_cli_version()` correctly detects both the matching-version case and a simulated
  drifted-version case (verified by temporarily pinning to a wrong version string and confirming
  the warning fires). **Verified** the matching case live; drift case verified by temporarily
  editing `CLAUDE_CLI_VERSION_PINNED` to a wrong string and confirming the warning logs.
- The smoke-test script runs standalone against the real installed CLI and exits nonzero on any
  assertion failure — verified by actually running it, including once with a deliberately broken
  assertion to confirm it fails loudly rather than passing silently. **Verified twice**: the
  first real run caught a genuine bug (the `system`/`init`-is-always-first assumption, see above)
  and correctly failed with exit code 1; a standalone reproduction of `main()`'s exact
  try/except/`sys.exit(1)` shape with an injected failing check also printed `[FAIL]` and exited
  1. All 5 checks pass on the current code (`basic one-shot`, `version`, `invalid --model`,
  `bad args`, `long-line`).
