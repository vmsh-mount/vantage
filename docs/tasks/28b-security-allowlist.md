# 28b — Security: Scoped Allowlist + Fail-Closed Permission Mode

**Depends on:** 28a (one-shot runner core — this task uses its `extra_args` seam)
**Unlocks:** 28c, 28e (both build the interactive/web-search capability on top of this task's
scoping mechanism, never around it)

## Goal

Make invariant #2 (planning-phase2.md §2) real, not aspirational: a `claude` subprocess spawned
by bridge-server must be unable to reach `.env`, unable to touch any tool beyond an explicit,
reviewable allowlist, and must **fail closed** (deny) on anything else — never hang waiting for a
prompt that can't be answered, never silently fall back to broad access.

## Scope

**Real constraints discovered live before writing any code — two of them force a correction to
planning-phase2.md's own invariant #2 text, not just to this task's design:**

1. **A bare `claude -p` inherits the *user's* ambient config wholesale** — confirmed live: it
   connects to every MCP server in the interactive account's own config (in this environment:
   Tolaria notes and Google Drive, **including Google Drive's `create_file`/write tools**) and
   exposes the full built-in tool set (`Bash`, `Read`, `Write`, `Edit`, `Task`, …). None of that
   is Vantage-related; all of it becomes reachable to "the Vantage agent" unless explicitly
   stripped. This is a bigger gap than invariant #2 described — it names `.env`/credentials as
   the risk, but a bare spawn hands the agent the *entire ambient environment*, including
   personal tools with zero relationship to portfolio data.
2. **`--strict-mcp-config` + an explicit `--mcp-config` pointing only at Vantage's own MCP server
   (task 26) fully solves #1** — confirmed live: `mcp_servers` in the resulting session is
   exactly `[{"name": "vantage", ...}]`, tools exactly the 9 from task 26, nothing ambient.
   `--mcp-config` accepts an **inline JSON string**, not just a file path — no tempfile needed.
3. **`--tools ""` disables every built-in tool** (`Bash`, `Read`, `Write`, `Edit`,
   `NotebookEdit`, `Task`, `WebFetch`, `WebSearch`, …) — confirmed live, leaving only the
   explicitly-configured MCP tools. None of Vantage's use cases need any built-in tool.
4. **By default, every MCP tool call in non-interactive `-p` mode is denied** — even a harmless
   read tool. Confirmed live (`get_dashboard` with no `--allowedTools`): `"Claude requested
   permissions to use mcp__vantage__get_dashboard, but you haven't granted it yet."` This is
   already fail-closed by construction (no TTY exists to prompt on), but the plan asks for an
   *explicit* mode rather than relying on that implicit behavior.
5. **`--permission-mode dontAsk`** is the explicit mode that matches invariant #2's wording —
   confirmed live: a non-allowlisted tool is denied with `"...blocked because Claude Code is
   running in don't ask mode"`, deterministic, never a hang, and it does not fall back to
   allowing anything.
6. **`--allowedTools` genuinely partitions the surface** — confirmed live in one real run: the 8
   read tools (`get_dashboard`, `get_risk`, `get_trend`, `get_thresholds`,
   `get_tax_suggestions`, `get_volatility_stops`, `get_benchmark`, `get_status`) succeeded while
   `set_threshold` — deliberately left off the allowlist for this test — was denied in the same
   run, and independently confirmed via `GET /api/thresholds` that nothing was actually written.
7. **The critical finding — planning-phase2.md §2(b) is wrong as written.** It says `.env` is
   protected by "a working directory that does not contain it." **Tested directly and disproven**:
   with `Read` allowlisted (a deliberate defense-in-depth test, not the shipped default — see
   below) and `cwd` set to an unrelated directory, the agent successfully read
   `bridge-server/.env` **by its absolute path** and displayed the real `PAYTMMONEY_API_KEY`,
   `PAYTMMONEY_API_SECRET`, live access tokens, and `SMTP_PASSWORD` in its output. Working
   directory does **not** sandbox absolute-path file access — there is no path-based enforcement
   to rely on at all. **The only real protection is tool exclusion**: `Read` (and `Bash`, `Write`,
   `Edit`, `NotebookEdit`) must never be reachable by this agent, full stop — not "scoped away
   from `.env`," genuinely absent. `planning-phase2.md` §2(b) is corrected alongside this task to
   describe the mechanism that actually works, rather than the disproven cwd-scoping claim.

**`bridge-server/app/agent_security.py`** (new):
- `VANTAGE_MCP_URL` — built from `settings` (new `bridge_server_port` setting, default 8000).
- `READ_ONLY_TOOLS` — the 8 `mcp__vantage__get_*`/`get_status` tool names.
- `WRITE_TOOLS` — `mcp__vantage__set_threshold`, kept separate so allowing it is always an
  explicit per-call-site choice (task 29's job), never an accidental default.
- `DANGEROUS_BUILTIN_TOOLS` — `Bash`, `Read`, `Write`, `Edit`, `NotebookEdit`, `Task` — passed to
  `--disallowedTools` as **defense-in-depth on top of** `--tools ""`, not instead of it: belt and
  suspenders in case a future call site loosens `--tools` without noticing what that reopens.
- `def build_scoped_extra_args(*, allow_write: bool = False) -> list[str]` — returns the full
  `extra_args` list for `agent_runner.run_one_shot`: `--strict-mcp-config`, `--mcp-config
  <inline vantage-only JSON>`, `--tools ""`, `--allowedTools <read tools [+ set_threshold if
  allow_write]>`, `--disallowedTools <dangerous builtins>`, `--permission-mode dontAsk`.

## Out of scope

- No WebSocket/interactive session (28c) — this task only shapes the `extra_args` a one-shot run
  is launched with.
- No web search/fetch tool (28e) — that task adds its own scoped entry to the allow/deny lists
  here, doesn't rebuild this mechanism.
- **Correcting `.env`'s handling doesn't mean adding path-based enforcement** — the finding above
  is that path-based enforcement doesn't exist/isn't reliable; the fix is tool exclusion, which
  this task already does. No attempt is made to "properly" sandbox `Read` to a subdirectory —
  that path was tested and shown not to hold.
- `set_threshold` is not part of the default allowlist this task ships — `allow_write=True` exists
  as a deliberate, visible opt-in for whichever future call site (task 29) decides to use it, not
  a default this task should silently choose on task 29's behalf.

## Acceptance criteria

- A one-shot run using `build_scoped_extra_args()` connects to exactly Vantage's own MCP server
  and no ambient ones — verified via the real `init` event's `mcp_servers` field. **Verified**:
  `mcp_servers` was exactly `[{"name": "vantage", ...}]`, all 9 tools `mcp__vantage__*`.
- The 8 read tools succeed and `set_threshold` is denied in the same real run when
  `allow_write=False` (the default) — verified against real DB state, not just the agent's own
  narration. **Verified, after fixing a real bug in the check itself**: the first version of this
  verification queried `GET /api/thresholds`, which (per `routers/thresholds.py`'s
  `list_thresholds`) only returns a row for symbols with a matching `Holding` — a synthetic test
  symbol with no real holding can **never** appear there, write or no write. That made the check
  pass vacuously regardless of whether the security mechanism actually worked. Fixed by querying
  the `Threshold` table directly; re-verified and confirmed no row exists after a denied call.
- With `allow_write=True`, `set_threshold` succeeds — **verified directly against the `Threshold`
  table** (same fix as above) after the same vacuous-pass bug affected this check too.
- A prompt attempting to read `bridge-server/.env` by absolute path, run through
  `build_scoped_extra_args()`'s actual output (not the earlier defense-in-depth test that
  deliberately allowlisted `Read`), is denied — confirmed no credential content appears anywhere
  in the event stream. **Verified**: the agent didn't even attempt the tool (Read isn't offered
  as available at all under the default config), responding "I'm not able to read `.env` files —
  they typically contain secrets like API keys, tokens, and credentials."
- `planning-phase2.md` §2(b) updated to describe the verified mechanism (tool exclusion) instead
  of the disproven cwd-scoping claim. **Done.**
