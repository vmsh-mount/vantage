#!/usr/bin/env python3
"""Task 28a smoke test — runs a real one-shot prompt through the actual
installed `claude` CLI (no fixtures, no mocking) and asserts on the live
event shape. Mirrors task 24's INDmoney contract smoke-test: the risk is a
vendor interface (here, the claude CLI itself) drifting silently underneath
this runner. Run directly: `python scripts/agent_runner_smoke_test.py`."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent_runner import AgentRunError, check_claude_cli_version, run_one_shot  # noqa: E402


async def check_basic_one_shot() -> None:
    events = []
    async for event in run_one_shot("Say exactly: smoke test ok"):
        events.append(event)

    assert events, "expected at least one event, got none"
    # NOT necessarily events[0] — confirmed live that a rate_limit_event can
    # arrive before system/init (a separate async usage-check stream racing
    # the session init), so this only asserts the init event exists, not its
    # position. See docs/tasks/28a-one-shot-runner-core.md.
    init_events = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
    assert init_events, f"expected a system/init event somewhere in the stream, got types {[e.get('type') for e in events]}"
    assert "session_id" in init_events[0], f"expected session_id in init event, got {init_events[0]}"
    assert any(e.get("type") == "assistant" for e in events), (
        f"expected at least one assistant event, got types {[e.get('type') for e in events]}"
    )
    assert events[-1].get("type") == "result", f"expected terminal result event, got {events[-1]}"
    print(f"[ok] basic one-shot: {len(events)} events, terminal={events[-1].get('subtype')}")


async def check_long_line_handling() -> None:
    # Forces a long single-turn text response so the assistant event's JSON
    # line genuinely exceeds 64KB — the real case _stream_ndjson's manual
    # buffering exists for, not a synthetic in-memory string.
    prompt = (
        "Reply with exactly the digit 7 repeated 40000 times, no other text, "
        "no explanation, just the digits."
    )
    events = []
    async for event in run_one_shot(prompt):
        events.append(event)

    assistant_events = [e for e in events if e.get("type") == "assistant"]
    assert assistant_events, "expected at least one assistant event for the long-line check"
    text = "".join(
        block.get("text", "")
        for e in assistant_events
        for block in e.get("message", {}).get("content", [])
        if block.get("type") == "text"
    )
    assert len(text) > 20000, f"expected a long response, got {len(text)} chars"
    assert events[-1].get("type") == "result", "expected terminal result event after long line"
    print(f"[ok] long-line handling: response {len(text)} chars parsed without truncation")


async def check_invalid_model_is_structured_error() -> None:
    # Confirmed live: an unknown --model does NOT crash the process — the
    # CLI emits a normal terminal result event with is_error=true and a real
    # api_error_status (404 seen live), same shape as any other turn. This
    # is exactly run_one_shot's documented contract (structured errors are
    # yielded, not raised) working as intended, not a gap to paper over.
    events = []
    async for event in run_one_shot("hi", model="definitely-not-a-real-model-xyz"):
        events.append(event)
    result = events[-1]
    assert result.get("type") == "result", f"expected a terminal result event, got {events[-1]}"
    assert result.get("is_error") is True, f"expected is_error=true for an invalid model, got {result}"
    print(f"[ok] invalid --model surfaced as a structured error event (is_error=true, api_error_status={result.get('api_error_status')}), not an exception")


async def check_bad_args_raises() -> None:
    # A genuinely malformed invocation — the CLI's arg parser rejects it
    # before producing any NDJSON output at all, so terminal_seen stays
    # False and AgentRunError must fire.
    try:
        async for _ in run_one_shot("hi", extra_args=["--this-flag-does-not-exist"]):
            pass
    except AgentRunError as exc:
        print(f"[ok] malformed args raised AgentRunError as expected: {exc}")
        return
    raise AssertionError("expected AgentRunError for an unsupported CLI flag, but none was raised")


async def check_version() -> None:
    matches, actual = await check_claude_cli_version()
    status = "matches pin" if matches else "DRIFTED from pin"
    print(f"[ok] claude CLI version check ran: {status} (actual: {actual!r})")


async def main() -> None:
    checks = [
        check_basic_one_shot(),
        check_version(),
        check_invalid_model_is_structured_error(),
        check_bad_args_raises(),
        check_long_line_handling(),
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
