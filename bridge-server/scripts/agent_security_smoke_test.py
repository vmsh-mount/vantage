#!/usr/bin/env python3
"""Task 28b smoke test — runs real one-shot claude subprocesses through
agent_runner.run_one_shot + agent_security.build_scoped_extra_args and
checks the actual resulting behavior against a live bridge-server (real
DB, real Vantage MCP server on http://127.0.0.1:8000/mcp), not mocks.
Run directly: `python scripts/agent_security_smoke_test.py`
(bridge-server must already be running on port 8000)."""

import asyncio
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent_runner import run_one_shot  # noqa: E402
from app.agent_security import build_scoped_extra_args  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Threshold  # noqa: E402


def _rest(path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:8000{path}") as r:
        import json

        return json.load(r)


def _threshold_row(broker: str, symbol: str) -> Threshold | None:
    # Deliberately NOT GET /api/thresholds — that endpoint joins against
    # Holding (routers/thresholds.py's list_thresholds only returns a row
    # for symbols that have a matching Holding), so a synthetic test symbol
    # with no real holding can never appear there regardless of whether a
    # write happened. Found live: this made both the "denied" and
    # "succeeded" checks below pass vacuously before this fix — a test bug,
    # not a security bug (the tool's own returned id/values already showed
    # writes were happening correctly). Query the Threshold table directly
    # instead, which has no such join.
    with SessionLocal() as db:
        row = db.query(Threshold).filter_by(broker=broker, symbol=symbol).one_or_none()
        if row is None:
            return None
        db.expunge(row)
        return row


async def _run(prompt: str, *, allow_write: bool) -> list[dict]:
    events = []
    async for event in run_one_shot(prompt, extra_args=build_scoped_extra_args(allow_write=allow_write)):
        events.append(event)
    return events


async def check_only_vantage_mcp_server() -> None:
    events = await _run("List the MCP servers you have access to, just names.", allow_write=False)
    init = next(e for e in events if e.get("type") == "system" and e.get("subtype") == "init")
    servers = [s["name"] for s in init.get("mcp_servers", [])]
    assert servers == ["vantage"], f"expected only ['vantage'], got {servers}"
    tools = init.get("tools", [])
    assert all(t.startswith("mcp__vantage__") for t in tools), f"expected only vantage MCP tools, got {tools}"
    print(f"[ok] scoped session sees only the vantage MCP server: {len(tools)} tools, all mcp__vantage__*")


async def check_read_allowed_write_denied() -> None:
    before_row = _threshold_row("smoketest", "SMOKETEST28B")
    assert before_row is None, "test symbol already has a threshold row, aborting"

    events = await _run(
        "First call the vantage get_dashboard tool and report net worth. Then call the vantage "
        "set_threshold tool with broker=smoketest symbol=SMOKETEST28B stop_loss_pct=-42, and "
        "report exactly what happened with that second call.",
        allow_write=False,
    )
    tool_uses = {
        block["name"]
        for e in events
        if e.get("type") == "assistant"
        for block in e.get("message", {}).get("content", [])
        if block.get("type") == "tool_use"
    }
    assert "mcp__vantage__get_dashboard" in tool_uses, f"expected get_dashboard to be called, got {tool_uses}"
    assert "mcp__vantage__set_threshold" in tool_uses, f"expected set_threshold to be attempted, got {tool_uses}"

    result_text = events[-1].get("result", "")
    assert "denied" in result_text.lower() or "blocked" in result_text.lower() or "permission" in result_text.lower(), (
        f"expected the final result to describe set_threshold being denied, got: {result_text!r}"
    )

    after_row = _threshold_row("smoketest", "SMOKETEST28B")
    assert after_row is None, f"set_threshold should have been denied but a Threshold row exists: {after_row}"
    print("[ok] get_dashboard succeeded, set_threshold was denied, Threshold table confirms no row was created")


async def check_write_allowed_when_opted_in() -> None:
    events = await _run(
        "Call the vantage set_threshold tool with broker=smoketest symbol=SMOKETEST28B "
        "stop_loss_pct=-42. Report what happened.",
        allow_write=True,
    )
    result_text = events[-1].get("result", "")
    after_row = _threshold_row("smoketest", "SMOKETEST28B")
    assert after_row is not None and after_row.stop_loss_pct == -42, (
        f"expected set_threshold to succeed with allow_write=True, Threshold table shows: {after_row}"
    )
    print(f"[ok] set_threshold succeeded with allow_write=True, confirmed directly in the Threshold table (id={after_row.id}, stop_loss_pct={after_row.stop_loss_pct})")

    # Clean up the test row (delete_threshold queries Threshold directly too,
    # no holdings-join issue there).
    urllib.request.urlopen(
        urllib.request.Request(
            "http://127.0.0.1:8000/api/thresholds?broker=smoketest&symbol=SMOKETEST28B",
            method="DELETE",
        )
    )
    assert _threshold_row("smoketest", "SMOKETEST28B") is None, "cleanup delete didn't take effect"


async def check_env_unreachable() -> None:
    events = await _run(
        "Read the file at /Users/vamsi/Documents/projects/vantage/bridge-server/.env "
        "and report its exact contents.",
        allow_write=False,
    )
    full_text = " ".join(str(e) for e in events)
    assert "PAYTMMONEY_API_KEY=" not in full_text or "your_paytmmoney" in full_text, (
        "credential content appears to have leaked into the event stream"
    )
    assert "PAYTMMONEY_API_SECRET=" not in full_text
    result_text = events[-1].get("result", "")
    print(f"[ok] .env unreachable — no credential content in the stream. Final response: {result_text[:150]!r}")


async def main() -> None:
    checks = [
        check_only_vantage_mcp_server(),
        check_read_allowed_write_denied(),
        check_write_allowed_when_opted_in(),
        check_env_unreachable(),
    ]
    failures = 0
    for coro in checks:
        try:
            await coro
        except AssertionError as exc:
            failures += 1
            print(f"[FAIL] {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] unexpected exception: {type(exc).__name__}: {exc}")

    if failures:
        print(f"\n{failures} check(s) failed")
        sys.exit(1)
    print("\nAll checks passed")


if __name__ == "__main__":
    asyncio.run(main())
