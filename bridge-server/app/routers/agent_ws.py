"""Multi-turn WebSocket bridge to a real claude subprocess (task 28c,
planning-phase2.md §6.1). Bridge-server's first async subprocess-to-WS code
— everything through task 27 is sync `def` on a threadpool.

Spawn-per-turn design: each browser message triggers one task 28a
run_one_shot call, scoped by task 28b's build_scoped_extra_args, with
--resume added once a session exists. State (conversation history) lives in
the session file `claude` itself manages on disk, not in bridge-server
memory — chosen over a persistent bidirectional process because it reuses
run_one_shot almost verbatim and needs no subprocess registry/idle-timeout/
reconnect-to-existing-process logic. See docs/tasks/28c-multiturn-websocket.md
for the live testing that led here, including a methodology trap (a "secret
word" probe gave a false negative on context retention — safety-flavored
refusal, not real memory loss) and a real non-security finding (the auto-
memory habit fixed in agent_security.py's NO_MEMORY_SYSTEM_PROMPT)."""

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent_runner import AgentRunError, run_one_shot
from app.agent_security import build_scoped_extra_args
from app.db import SessionLocal
from app.models._util import utcnow
from app.run_context import forget_run, mark_touched_untrusted, reconcile_touched_rows, register_run

logger = logging.getLogger("vantage.agent_ws")

router = APIRouter()

# Task 35: any tool_use for one of these, seen anywhere on this connection,
# marks every write it makes from then on (this turn or a later one) as
# having touched untrusted content. Kept in sync with agent_security.py's
# own WEB_TOOLS.
_WEB_TOOL_NAMES = {"WebFetch", "WebSearch"}


def _event_uses_web_tool(event: dict) -> bool:
    """Same NDJSON assistant/tool_use shape the frontend's own AiPanel.tsx
    already parses (Anthropic Messages API format) — not a new event
    contract, just watched from the server side too."""
    if event.get("type") != "assistant":
        return False
    content = (event.get("message") or {}).get("content") or []
    return any(block.get("type") == "tool_use" and block.get("name") in _WEB_TOOL_NAMES for block in content)


@router.websocket("/ws/agent")
async def agent_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    session_id: str | None = None
    # Task 35: bridge-server's own per-connection correlator — see
    # app/run_context.py's docstring for why this, not Claude CLI's own
    # --resume session_id, is what gets threaded through to the /mcp
    # endpoint for provenance tagging.
    run_key = uuid.uuid4().hex
    register_run(run_key)

    try:
        while True:
            data = await websocket.receive_json()
            prompt = data.get("prompt")
            if not prompt:
                await websocket.send_json({"type": "error", "message": "missing 'prompt' field"})
                continue

            # Task 29: the panel is the one call site that opts into all
            # three flags — see agent_security.py finding #9 for why
            # allow_write/enable_ui_actions default on here specifically.
            extra_args = build_scoped_extra_args(
                allow_write=True, enable_web=True, enable_ui_actions=True, run_key=run_key
            )
            if session_id:
                extra_args = extra_args + ["--resume", session_id]

            # Task 35: the turn's start, used to scope reconcile_touched_rows
            # below to *this* turn's writes only — see run_context.py's
            # docstring (bug #2) for why this reconciliation pass exists at
            # all. Same utcnow() every Thesis/DecisionLog row's created_at
            # uses, so the comparison is apples-to-apples.
            turn_started_at = utcnow()
            try:
                # Each event is forwarded individually as it arrives — no
                # buffering between the subprocess and the browser, so a
                # slow client's await on send_json naturally back-pressures
                # this loop (and therefore the next stdout read) instead of
                # events piling up in memory. Verified live, not assumed
                # (see the smoke test's backpressure check).
                async for event in run_one_shot(prompt, extra_args=extra_args):
                    if event.get("type") == "system" and event.get("subtype") == "init":
                        session_id = event.get("session_id")
                    if _event_uses_web_tool(event):
                        mark_touched_untrusted(run_key)
                    await websocket.send_json(event)
            except AgentRunError as exc:
                logger.warning("agent_ws turn failed: %s", exc)
                await websocket.send_json({"type": "error", "message": str(exc)})
            finally:
                with SessionLocal() as db:
                    reconcile_touched_rows(db, run_key, turn_started_at)
    except WebSocketDisconnect:
        pass
    finally:
        forget_run(run_key)
