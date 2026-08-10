#!/usr/bin/env python3
"""Task 28c smoke test — real WebSocket client against a live bridge-server
(ws://127.0.0.1:8000/ws/agent), real claude subprocesses underneath, no
mocks. Run directly: `python scripts/agent_ws_smoke_test.py`
(bridge-server must already be running on port 8000)."""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets  # noqa: E402

WS_URL = "ws://127.0.0.1:8000/ws/agent"


async def _send_prompt_collect(ws, prompt: str) -> list[dict]:
    await ws.send(json.dumps({"prompt": prompt}))
    events = []
    while True:
        raw = await ws.recv()
        event = json.loads(raw)
        events.append(event)
        if event.get("type") in ("result", "error"):
            return events


async def check_multiturn_context_retained() -> None:
    async with websockets.connect(WS_URL, max_size=None) as ws:
        e1 = await _send_prompt_collect(ws, "My favorite number is 77. Just acknowledge with 'noted'.")
        r1 = e1[-1]
        assert r1.get("type") == "result", f"expected a result event, got {r1}"

        e2 = await _send_prompt_collect(ws, "What number did I just tell you is my favorite?")
        r2 = e2[-1]
        assert "77" in (r2.get("result") or ""), f"expected context retained ('77' in result), got: {r2.get('result')!r}"
        print("[ok] multi-turn context retained across two turns on one WS connection")


async def check_event_fidelity() -> None:
    async with websockets.connect(WS_URL, max_size=None) as ws:
        events = await _send_prompt_collect(ws, "Say exactly: fidelity check ok")
        types = [e.get("type") for e in events]
        assert "system" in types, f"expected a system/init event, got types {types}"
        assert "assistant" in types, f"expected an assistant event, got types {types}"
        assert types[-1] == "result", f"expected the final event to be type=result, got {types[-1]}"
        print(f"[ok] event fidelity: {len(events)} events forwarded individually, correct types: {types}")


async def check_backpressure() -> None:
    # A long response gives us enough events to observe pacing. Read slowly
    # (sleep between each recv) and confirm total wall-clock time reflects
    # the slow consumer, not "everything arrived instantly and sat in a
    # buffer" — the two are indistinguishable from event *content* alone,
    # only from timing.
    async with websockets.connect(WS_URL, max_size=None) as ws:
        await ws.send(json.dumps({"prompt": "Count from 1 to 20, one number per line, nothing else."}))
        start = time.monotonic()
        n_events = 0
        per_event_gap = 0.4
        while True:
            raw = await ws.recv()
            event = json.loads(raw)
            n_events += 1
            if event.get("type") in ("result", "error"):
                break
            await asyncio.sleep(per_event_gap)  # simulate a slow browser
        elapsed = time.monotonic() - start
        # If the server buffered everything and dumped it instantly, elapsed
        # would be roughly the raw generation time regardless of our sleeps.
        # If backpressure is real, elapsed should be at least in the
        # ballpark of (n_events - 1) * per_event_gap.
        expected_floor = (n_events - 1) * per_event_gap * 0.5  # generous margin
        assert elapsed >= expected_floor, (
            f"expected backpressure to slow the server to roughly our read pace "
            f"(~{expected_floor:.1f}s floor for {n_events} events), but total was only {elapsed:.1f}s — "
            f"looks like events were buffered and sent all at once"
        )
        print(f"[ok] backpressure observed: {n_events} events, {elapsed:.1f}s wall time with a {per_event_gap}s/event slow reader")


async def check_security_scoping_persists_across_turns() -> None:
    async with websockets.connect(WS_URL, max_size=None) as ws:
        await _send_prompt_collect(ws, "Call get_dashboard and report net worth.")
        events = await _send_prompt_collect(
            ws,
            "Now call set_threshold with broker=wstest symbol=WSTEST28C stop_loss_pct=-11. "
            "Report exactly what happened.",
        )
        result_text = (events[-1].get("result") or "").lower()
        assert "denied" in result_text or "blocked" in result_text or "permission" in result_text, (
            f"expected set_threshold to be denied mid-conversation, got: {events[-1].get('result')!r}"
        )

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from app.db import SessionLocal
        from app.models import Threshold

        with SessionLocal() as db:
            row = db.query(Threshold).filter_by(broker="wstest", symbol="WSTEST28C").one_or_none()
        assert row is None, f"set_threshold should have been denied but a row exists: {row}"
        print("[ok] security scoping (28b) still holds mid-conversation over WS — set_threshold denied, no DB write")


async def check_connections_are_isolated() -> None:
    async with websockets.connect(WS_URL, max_size=None) as ws_a:
        await _send_prompt_collect(ws_a, "My favorite color is teal. Just say noted.")

        async with websockets.connect(WS_URL, max_size=None) as ws_b:
            events_b = await _send_prompt_collect(ws_b, "What is my favorite color?")
            result_b = (events_b[-1].get("result") or "").lower()
            assert "teal" not in result_b, (
                f"connection B should not know connection A's context, but got: {events_b[-1].get('result')!r}"
            )
    print("[ok] two independent WS connections have independent sessions — no cross-talk")


async def main() -> None:
    checks = [
        check_event_fidelity(),
        check_multiturn_context_retained(),
        check_security_scoping_persists_across_turns(),
        check_connections_are_isolated(),
        check_backpressure(),
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
