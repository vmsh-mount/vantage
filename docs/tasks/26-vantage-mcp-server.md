# 26 — Vantage MCP Server

**Depends on:** 25 (deterministic fact tools)
**Unlocks:** 28 (Claude Code runner — the agent that actually calls these tools)

## Goal

Stand up Vantage's own MCP server — **co-hosted inside the existing FastAPI `bridge-server`
process**, not a separate stdio child of `claude` (planning-phase2.md §4) — exposing the
deterministic backend as agent-callable tools: read tools over everything task 19–25 already
built, plus one real write/action tool.

## Scope

**Real constraint discovered before writing code:** planning-phase2.md §4 describes "read tools
+ UI-action tools," where a UI-action is meant to **bridge an agent tool call onto the existing
WebSocket to the React SPA** (e.g. highlight a row, open a modal, scroll to a section). That
WebSocket doesn't exist anywhere in this codebase yet (`grep -rn "WebSocket" bridge-server/
deck-app/` — zero hits) — building it is explicitly task 28's charter ("`asyncio.
create_subprocess_exec` + WS streaming... new territory," "multi-week subsystem"). Task 26
cannot honestly ship browser-push UI actions without that WS existing first.

**Rescoped accordingly:** ship every read tool now (full value, zero blockers), plus the one
write/action tool that's real and useful *without* a live browser bridge — updating a holding's
stop-loss/target threshold, which already has a working CRUD path (`app/routers/thresholds.py`).
The agent can propose "set SWIGGY's stop to −7%" and actually do it; the dashboard reflects it
on next load, same as if you'd edited it by hand — no push needed for that to be genuinely
useful. Literal browser-push actions (highlight/navigate/scroll) stay explicitly out of scope
here and move to task 28, once the WS it needs actually exists.

**Transport:** streamable-HTTP (`mcp.server.fastmcp.FastMCP`'s `streamable_http_app()`), mounted
onto the existing FastAPI `app` at `/mcp`. Matches what task 24 already validated *as a client*
against INDmoney's own MCP server, and is FastMCP's modern default — not the older SSE-only
transport, though the SDK still supports that path too.

**No auth on this MCP endpoint.** Invariant #4 (local, single-user) — this mirrors every existing
`/api/*` route in this codebase, none of which have auth either; the security boundary is "it's
your own laptop," unchanged by adding one more mounted app to the same process bound to
`127.0.0.1`. Not an oversight — a decision consistent with what's already shipped.

**Tools exposed** (each wraps an existing, already-verified function directly — no logic
duplicated, no separate HTTP round-trip back into the same process):

Read:
- `get_dashboard` → `routers.dashboard.get_dashboard`
- `get_risk` → `routers.risk.get_risk` (concentration flags, region split)
- `get_trend(days=30)` → `routers.trend.get_trend`
- `get_thresholds` → `routers.thresholds.list_thresholds`
- `get_tax_suggestions` → `tax.suggestions.get_tax_suggestions` (task 22)
- `get_volatility_stops` → `facts.volatility.get_volatility_stops` (task 25, real INDmoney OHLC)
- `get_benchmark` → `facts.benchmark.get_benchmarks` (task 25, real INDmoney OHLC + NIFTY)
- `get_status` → `routers.status.get_status` (broker health/token status)

Write/action:
- `set_threshold(broker, symbol, stop_loss_pct=None, target_pct=None, notes=None)` →
  `routers.thresholds._upsert_threshold`. Only a local `Threshold` row — never touches a broker,
  never places or modifies an order (invariant #1 holds trivially: this task's write surface
  doesn't go anywhere near `PAYTMMONEY_*`/`INDMONEY_*` credentials or endpoints at all).

Each MCP tool function opens its own `SessionLocal()` (mirrors `get_db`'s pattern, since MCP
tools aren't FastAPI request handlers and don't get `Depends` injection) and closes it when done.

**New file:** `bridge-server/app/vantage_mcp.py`. **Modified:** `bridge-server/app/main.py`
(mounts the MCP app), `requirements.txt` if a new extra is needed for `FastMCP` (unlikely —
`mcp>=1.28` from task 24 already includes `mcp.server.fastmcp`).

**Two real integration issues found and fixed while wiring this up, not assumed away:**
1. **Mounting `streamable_http_app()` into FastAPI doesn't run its lifespan.** The Starlette app
   `FastMCP.streamable_http_app()` returns carries its own `lifespan=lambda app:
   self.session_manager.run()`, but `app.mount(...)` never triggers a mounted sub-app's lifespan —
   Starlette only dispatches the ASGI `lifespan` scope to the top-level app. Without a fix every
   MCP request would 500 with "Task group is not initialized." Fixed by entering
   `vantage_mcp.session_manager.run()` inside bridge-server's *own* `lifespan` in `main.py`,
   alongside `init_db()`/`start_scheduler()`, rather than relying on the sub-app's own lifespan.
2. **MCP's `structuredContent` must be a JSON object**, not a bare array — a tool that returns a
   Python list gets it silently auto-wrapped as `{"result": [...]}` by the SDK. `get_tax_
   suggestions`, `get_volatility_stops`, and `get_benchmark` return lists, so each explicitly
   returns `{"suggestions": [...]}` instead of relying on the generic auto-wrap — both a more
   predictable contract for a tool consumer and consistent with the REST schemas' own
   `suggestions` field name (`TaxSuggestionsOut`, `VolatilityStopsOut`, `BenchmarkOut`).

## Out of scope

- Browser-push UI-action tools (highlight/navigate/scroll) — needs task 28's WebSocket runner
  first; see Scope above.
- No auth/OAuth on the Vantage MCP endpoint itself (see Scope above) — this is the *server* side
  for Vantage's own tools, unrelated to task 24's client-side OAuth against INDmoney's server.
- No new write tools beyond thresholds (e.g. manual-holdings CRUD, statement upload) — thresholds
  is the one directly relevant to the "propose a stop, then set it" workflow task 29 wants;
  expanding the write surface further is a call for whenever the panel (task 29) actually needs
  it, not preemptively here.
- No changes to the deterministic logic itself in dashboard/risk/trend/tax/facts — this task only
  adds an MCP-shaped door onto what already exists and is already verified.

## Acceptance criteria

- The MCP server is reachable over real streamable-HTTP at `http://127.0.0.1:8000/mcp` while
  bridge-server is running — verified with a real MCP client session (the same `mcp` SDK used as
  task 24's client), not just "the mount didn't crash on import." **Verified**: `list_tools()`
  returned all 9 registered tools over a live connection.
- Every read tool, called through a real MCP `ClientSession.call_tool`, returns the same data the
  equivalent REST endpoint returns for the same DB state — spot-checked, not assumed. **Verified**:
  `get_dashboard`, `get_risk`, `get_trend`, `get_thresholds`, `get_tax_suggestions`, `get_status`,
  and `get_benchmark` were called live and diffed byte-for-byte (`benchmark` ignoring `as_of`
  timestamps) against their REST equivalents on identical DB state — all matched exactly.
  `get_volatility_stops` was run end-to-end over MCP (24/24 real holdings resolved, ~2m10s —
  consistent with the documented rate-limit backoff cost, not a regression).
- `set_threshold` actually writes to the `Threshold` table through a real MCP tool call, and
  `get_thresholds` (or the existing `/api/thresholds` REST route) reflects it immediately after.
  **Verified**: set SWIGGY's `stop_loss_pct` to -7.5 via a real MCP `call_tool`, confirmed it via
  a REST `GET /api/thresholds` call immediately after, then deleted the test row via
  `DELETE /api/thresholds` to leave real data clean.
- No tool on this server can place, modify, or cancel a broker order, or read `PAYTMMONEY_*`/
  `INDMONEY_*` credentials — confirmed by inspection of `vantage_mcp.py`, not just asserted.
  **Verified**: `grep` for `PAYTMMONEY|INDMONEY|.env|api_key|api_secret|access_token|order` across
  the file matches only docstring prose stating the invariant, no actual credential access.
