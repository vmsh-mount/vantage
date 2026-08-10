"""Task 35 (planning-phase2.md §7.1): per-connection provenance tracking for
the panel's write tools (add_thesis_entry, log_decision).

The real plumbing problem this solves: app/vantage_mcp.py's own docstring
already notes MCP tools don't get FastAPI's `Depends` injection, and beyond
that, the actual tool call arrives at bridge-server's own /mcp endpoint via
a live HTTP request made *by the spawned `claude` subprocess* — a genuinely
separate OS process from the one running agent_ws.py's WS loop. There is no
call-stack/task relationship between "the WS handler observed a WebFetch
tool_use event in the NDJSON stream" and "the /mcp endpoint is now handling
a log_decision call" — a bare contextvars.ContextVar set once in the WS
handler's own coroutine would NOT be visible there, because the request
that arrives at /mcp is dispatched as its own independent ASGI task, not a
child task of the WS coroutine. Confirmed by inspecting the actual
subprocess/HTTP architecture before implementing (task 28a/28c), not
assumed.

The fix used here: give each WS connection a bridge-server-generated
`run_key` (a plain uuid4 hex — deliberately NOT Claude CLI's own `--resume`
session_id, which isn't known until *after* the first turn's `system init`
event streams back, a chicken-and-egg problem for tagging any write made
during that very first turn). agent_security.build_scoped_extra_args bakes
`run_key` into the per-connection MCP config URL's query string; since the
`claude` CLI's MCP client just re-uses that exact URL string for every
request in the session (confirmed live), every /mcp request the subprocess
makes carries it. RunContextMiddleware reads it off the query string and
sets a ContextVar for the duration of that single request.

**Two real bugs found and fixed live** (docs/tasks/35-memory-poisoning-defenses.md
has the full trace):

1. The first implementation used Starlette's `BaseHTTPMiddleware`. Live
   testing (a real WS session calling WebSearch then log_decision) showed
   the middleware's own debug logging correctly saw `touched=True` for the
   log_decision request, yet the persisted DecisionLog row still came back
   `touched_untrusted_content: false`. Root cause: `BaseHTTPMiddleware.dispatch`
   runs the downstream ASGI app via an internal `anyio` task group — a
   well-known Starlette gotcha where contextvars set in `dispatch` do NOT
   reliably propagate into the wrapped app's own task, since it isn't a
   plain nested `await`, it's a separately-scheduled task. Fixed by writing
   this as a **plain ASGI middleware** instead (a `__call__(self, scope,
   receive, send)` that calls `await self.app(...)` directly, no
   BaseHTTPMiddleware, no task group) — that keeps everything in one task.

2. Even after that fix, the exact same test still failed when the model
   called WebSearch and log_decision **as two tool_use blocks in the same
   assistant turn**, dispatched by the `claude` CLI essentially in
   parallel. This is a genuine, inherent race, not a bug in this module: a
   loopback TCP connection for the log_decision HTTP call can beat
   agent_ws.py's own stdout-read scheduling to notice the WebSearch
   tool_use event and call mark_touched_untrusted first — there is no
   ordering guarantee between "we finished reading a stdout line" and "the
   subprocess's own HTTP client finished a TCP round-trip," even though
   both were triggered by the same model turn. reconcile_touched_rows below
   closes this deterministically: called once after every turn finishes
   (by which point is_touched_untrusted(run_key) reflects everything that
   turn actually did), it retroactively flips touched_untrusted_content on
   any row *this turn* wrote that lost the race — scoped to rows created
   at-or-after that turn's start, so an earlier, already-settled turn's
   clean writes are never touched. Re-verified live after both fixes: the
   same same-turn-parallel-calls test now correctly persists
   touched_untrusted_content: true."""

import contextvars
from datetime import datetime
from urllib.parse import parse_qs

from sqlalchemy.orm import Session

from app.models import DecisionLog, Thesis

# run_key -> whether this WS connection has seen a WebFetch/WebSearch
# tool_use event yet. Written by agent_ws.py's WS loop in real time (as
# events stream past); read by RunContextMiddleware on every /mcp request.
# Module-level, not per-request — this is exactly the shared state the two
# sides need to correlate through.
_TOUCHED_UNTRUSTED: dict[str, bool] = {}

current_run_key: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_run_key", default=None)
current_touched_untrusted: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "current_touched_untrusted", default=False
)


def register_run(run_key: str) -> None:
    """Called once per WS connection, before its first turn."""
    _TOUCHED_UNTRUSTED[run_key] = False


def mark_touched_untrusted(run_key: str) -> None:
    _TOUCHED_UNTRUSTED[run_key] = True


def is_touched_untrusted(run_key: str) -> bool:
    return _TOUCHED_UNTRUSTED.get(run_key, False)


def forget_run(run_key: str) -> None:
    """Called when a WS connection closes — keeps this dict from growing
    unboundedly across a long-running bridge-server process serving many
    panel sessions over time."""
    _TOUCHED_UNTRUSTED.pop(run_key, None)


def reconcile_touched_rows(db: Session, run_key: str, since: datetime) -> None:
    """Closes the real, live-confirmed same-turn race documented in this
    module's docstring (bug #2). Called by agent_ws.py once after each turn
    finishes. If this run has touched untrusted content by now, retroactively
    flips touched_untrusted_content=True on any row *this run_key wrote
    during this turn* (created_at >= since) that's still False — never an
    earlier turn's already-settled rows, so a clean write made before this
    connection ever saw untrusted content is never wrongly quarantined
    after the fact."""
    if not is_touched_untrusted(run_key):
        return
    for model in (Thesis, DecisionLog):
        db.query(model).filter(
            model.run_session_id == run_key,
            model.touched_untrusted_content.is_(False),
            model.created_at >= since,
        ).update({"touched_untrusted_content": True}, synchronize_session=False)
    db.commit()


class RunContextMiddleware:
    """Plain ASGI middleware (not BaseHTTPMiddleware — see the module
    docstring's "real bug found and fixed live" for why that matters here).
    Reads `run_key` off the query string of every request under /mcp and
    sets ContextVars (run_key + touched_untrusted_content, snapshotted at
    the moment this request arrived) for MCP write tools to read when
    constructing a Thesis/DecisionLog row. A no-op for every other path,
    and for non-HTTP scopes (the /ws/agent WebSocket)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        query_params = parse_qs((scope.get("query_string") or b"").decode())
        run_key = (query_params.get("run_key") or [None])[0]
        touched = is_touched_untrusted(run_key) if run_key else False

        key_token = current_run_key.set(run_key)
        touched_token = current_touched_untrusted.set(touched)
        try:
            await self.app(scope, receive, send)
        finally:
            current_run_key.reset(key_token)
            current_touched_untrusted.reset(touched_token)
