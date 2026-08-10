"""One-shot Claude Code runner core (task 28a, planning-phase2.md §6.1).
Launches a real `claude` CLI subprocess in one-shot (`-p`) mode and streams
its `stream-json` output as parsed events. Deliberately minimal: no
WebSocket (28c), no permission-mode/allowlist enforcement (28b — this
module's `extra_args` is a pass-through seam for that, not a security
boundary), no multi-turn/resume (28c), no DB/concurrency handling (28d).

Real constraints confirmed live against claude CLI 2.1.121 before writing
this module (see docs/tasks/28a-one-shot-runner-core.md):
- `--output-format stream-json` requires `--verbose` alongside `-p`, or the
  CLI refuses to start.
- The terminal event is `{"type": "result", ...}` — the correct point to
  stop reading, not process EOF (which can lag slightly).
- A single NDJSON line can exceed 64KB (a long assistant response embeds a
  long single-line JSON object), which is past asyncio.StreamReader.
  readline()'s default buffer limit — this module reads raw chunks and
  splits on newlines itself instead."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.config import settings

logger = logging.getLogger("vantage.agent_runner")

CLAUDE_CLI_VERSION_PINNED = "2.1.121"
READ_CHUNK_SIZE = 65536


class AgentRunError(RuntimeError):
    """Raised only when the claude subprocess never produced a terminal
    `result` event at all (crashed, bad args, killed) — a `result` event
    with is_error=true is a legitimate structured outcome, yielded normally
    rather than raised, so callers can inspect it themselves."""


async def _stream_ndjson(stream: asyncio.StreamReader) -> AsyncIterator[dict[str, Any]]:
    buffer = bytearray()
    while True:
        chunk = await stream.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)
        while (newline_idx := buffer.find(b"\n")) != -1:
            line = bytes(buffer[:newline_idx])
            del buffer[: newline_idx + 1]
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Non-JSON line from claude stdout, skipping: %r", line[:200])
    if buffer.strip():
        try:
            yield json.loads(bytes(buffer))
        except json.JSONDecodeError:
            logger.warning(
                "Trailing non-JSON data from claude stdout, discarding: %r", bytes(buffer)[:200]
            )


async def run_one_shot(
    prompt: str,
    *,
    model: str | None = None,
    cwd: str | None = None,
    extra_args: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yields one parsed NDJSON event dict at a time, as they actually
    arrive from the subprocess. Stops at the first `type == "result"` event
    (the documented terminal event) rather than waiting for stdout EOF.

    extra_args is a deliberate pass-through seam: 28b appends
    --permission-mode/--allowedTools/--disallowedTools here rather than
    this function growing security-specific parameters directly."""
    args = [
        settings.claude_cli_path,
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if model:
        args += ["--model", model]
    if extra_args:
        args += extra_args

    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    terminal_seen = False
    try:
        async for event in _stream_ndjson(process.stdout):
            yield event
            if event.get("type") == "result":
                terminal_seen = True
                break
    finally:
        # Whether we broke out early on the result event or the stream just
        # ended, make sure the process is actually reaped rather than left
        # as a zombie — and don't let a hung process block forever.
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    if not terminal_seen:
        stderr_text = (await process.stderr.read()).decode(errors="replace").strip()
        raise AgentRunError(
            f"claude exited (code {process.returncode}) without a terminal result event. "
            f"stderr: {stderr_text or '(empty)'}"
        )


async def check_claude_cli_version() -> tuple[bool, str]:
    """Returns (matches_pin, actual_version_string). Never raises on drift —
    a version bump upstream shouldn't brick bridge-server outright — but
    logs loudly, since a silently-drifted CLI is exactly the kind of vendor
    interface risk task 24's INDmoney contract smoke-test exists to catch
    for a different dependency."""
    process = await asyncio.create_subprocess_exec(
        settings.claude_cli_path,
        "--version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    actual = stdout_bytes.decode(errors="replace").strip()

    if process.returncode != 0:
        logger.error(
            "claude --version failed (code %s): %s",
            process.returncode,
            stderr_bytes.decode(errors="replace").strip(),
        )
        return False, actual

    matches = actual.startswith(CLAUDE_CLI_VERSION_PINNED)
    if not matches:
        logger.warning(
            "claude CLI version drift: pinned %r, actual %r — agent_runner was validated "
            "against the pinned version; behavior on a different version is unverified.",
            CLAUDE_CLI_VERSION_PINNED,
            actual,
        )
    return matches, actual
