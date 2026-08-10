#!/usr/bin/env python3
"""Task 28d smoke test — real concurrent SQLite writers (threading, real
overlapping transactions, not simulated sequentially) and a real
mid-tool-call SIGKILL against a live claude subprocess. Run directly:
`python scripts/concurrency_smoke_test.py`."""

import asyncio
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent_runner import AgentRunError, run_one_shot  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Threshold  # noqa: E402

TEST_BROKER = "concurtest28d"


def _cleanup() -> None:
    with SessionLocal() as db:
        db.query(Threshold).filter_by(broker=TEST_BROKER).delete()
        db.commit()


def check_wal_and_busy_timeout() -> None:
    from sqlalchemy import text

    from app.db import engine

    with engine.connect() as conn:
        jm = conn.execute(text("PRAGMA journal_mode")).scalar()
        bt = conn.execute(text("PRAGMA busy_timeout")).scalar()
    assert jm == "wal", f"expected journal_mode=wal, got {jm}"
    assert bt == 5000, f"expected busy_timeout=5000, got {bt}"
    print(f"[ok] PRAGMA journal_mode={jm}, busy_timeout={bt}")


def check_concurrent_writers() -> None:
    """A slow writer holds the write lock open for 2s; a fast writer starts
    0.5s later, while the slow one still holds it. With WAL + busy_timeout
    both should succeed, with the fast writer's commit visibly delayed by
    roughly the remaining lock-hold time rather than failing immediately."""
    results = {}

    def slow_writer():
        db = SessionLocal()
        try:
            db.add(Threshold(broker=TEST_BROKER, symbol="SLOW", stop_loss_pct=-5))
            db.flush()  # issues the INSERT, acquiring the write lock, before commit
            time.sleep(2)
            db.commit()
            results["slow"] = "ok"
        except Exception as exc:  # noqa: BLE001
            results["slow"] = f"FAILED: {exc}"
        finally:
            db.close()

    def fast_writer():
        time.sleep(0.5)  # ensure slow_writer already holds the write lock
        start = time.monotonic()
        db = SessionLocal()
        try:
            db.add(Threshold(broker=TEST_BROKER, symbol="FAST", stop_loss_pct=-3))
            db.commit()
            elapsed = time.monotonic() - start
            results["fast"] = ("ok", elapsed)
        except Exception as exc:  # noqa: BLE001
            results["fast"] = ("FAILED", str(exc))
        finally:
            db.close()

    t1 = threading.Thread(target=slow_writer)
    t2 = threading.Thread(target=fast_writer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.get("slow") == "ok", f"slow writer failed: {results.get('slow')}"
    fast_status, fast_detail = results.get("fast", (None, None))
    assert fast_status == "ok", f"fast writer failed: {fast_detail}"
    # The fast writer started 0.5s in, while the slow one holds the lock
    # until ~2s — if busy_timeout is really making it wait rather than
    # erroring, its commit should take real time (roughly 1-1.5s), not be
    # near-instant.
    assert fast_detail > 0.8, (
        f"expected the fast writer's commit to be delayed by contention (~1-1.5s), "
        f"took only {fast_detail:.2f}s — doesn't look like it actually waited"
    )

    with SessionLocal() as db:
        slow_row = db.query(Threshold).filter_by(broker=TEST_BROKER, symbol="SLOW").one_or_none()
        fast_row = db.query(Threshold).filter_by(broker=TEST_BROKER, symbol="FAST").one_or_none()
    assert slow_row is not None and fast_row is not None, "both writes should be durable"
    print(f"[ok] concurrent writers: both succeeded, fast writer waited {fast_detail:.2f}s for the lock (no 'database is locked' error)")


async def check_mid_tool_call_crash() -> None:
    """Kills a real claude subprocess mid-turn (SIGKILL) and confirms
    run_one_shot surfaces a clean AgentRunError, then confirms a fresh turn
    immediately after still works (bridge-server itself isn't wedged)."""
    marker = "CRASHTEST28D"

    async def consume():
        events = []
        try:
            async for e in run_one_shot(
                f"Count slowly from 1 to 100, explaining each number's mathematical "
                f"properties in a full paragraph. marker={marker}"
            ):
                events.append(e)
        except AgentRunError as exc:
            return "AgentRunError", str(exc), events
        return "completed", None, events

    task = asyncio.create_task(consume())
    await asyncio.sleep(3)  # let it start generating

    ps_out = subprocess.check_output(["ps", "-eo", "pid,command"]).decode()
    pid = None
    for line in ps_out.splitlines():
        if marker in line and "claude" in line:
            pid = int(line.strip().split()[0])
            break
    assert pid is not None, "could not find the claude subprocess to kill — test setup issue, not the thing under test"

    os.kill(pid, signal.SIGKILL)
    outcome, err, events = await task
    assert outcome == "AgentRunError", f"expected AgentRunError after a mid-turn SIGKILL, got outcome={outcome!r}, events={len(events)}"
    print(f"[ok] mid-tool-call crash: SIGKILL on pid {pid} surfaced a clean AgentRunError ({len(events)} events collected before the kill): {err[:150]}")

    # Confirm bridge-server itself isn't wedged — a fresh turn right after
    # should work normally.
    events2 = []
    async for e in run_one_shot("Say exactly: recovery ok"):
        events2.append(e)
    assert events2[-1].get("type") == "result" and events2[-1].get("is_error") is False, (
        f"expected a clean successful turn after the crash, got {events2[-1]}"
    )
    print("[ok] a fresh run_one_shot call immediately after the crash succeeded normally — bridge-server not wedged")


async def main() -> None:
    _cleanup()
    failures = 0

    for check in [check_wal_and_busy_timeout, check_concurrent_writers]:
        try:
            check()
        except AssertionError as exc:
            failures += 1
            print(f"[FAIL] {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] unexpected exception: {type(exc).__name__}: {exc}")

    try:
        await check_mid_tool_call_crash()
    except AssertionError as exc:
        failures += 1
        print(f"[FAIL] {exc}")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"[FAIL] unexpected exception: {type(exc).__name__}: {exc}")

    _cleanup()

    if failures:
        print(f"\n{failures} check(s) failed")
        sys.exit(1)
    print("\nAll checks passed")


if __name__ == "__main__":
    asyncio.run(main())
