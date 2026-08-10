"""Shared helpers for the broker login scripts (paytmmoney_login.py,
indmoney_login.py, login.py) — restart/verify/env-writing logic that used
to be near-identical copies in each script, extracted here so there's
exactly one copy. Not meant to be run directly."""

import re
import subprocess
import time
from pathlib import Path

import httpx

BRIDGE_SERVER_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BRIDGE_SERVER_DIR / ".env"
LOG_DIR = BRIDGE_SERVER_DIR / "logs"
LOG_PATH = LOG_DIR / "server.log"
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8000
# Matched against `ps` output to find the running dev-server process — must
# stay in sync with how it's actually launched (see README/CLAUDE.md).
PROCESS_MATCH = "uvicorn app.main:app"


def write_env_var(key: str, value: str) -> None:
    content = ENV_PATH.read_text()
    line = f"{key}={value}"
    pattern = rf"^{key}=.*$"
    if re.search(pattern, content, flags=re.MULTILINE):
        content = re.sub(pattern, line, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{line}\n"
    ENV_PATH.write_text(content)


def restart_bridge_server() -> None:
    """Env vars are read once at process startup (pydantic-settings), so a
    freshly-written token has no effect until the process restarts. Kills
    whatever's already running on PROCESS_MATCH and relaunches it with the
    same invocation used throughout this project."""
    subprocess.run(["pkill", "-f", PROCESS_MATCH], check=False)
    time.sleep(1)

    LOG_DIR.mkdir(exist_ok=True)
    with open(LOG_PATH, "a") as log_file:
        subprocess.Popen(
            [".venv/bin/uvicorn", "app.main:app", "--host", BRIDGE_HOST, "--port", str(BRIDGE_PORT)],
            cwd=BRIDGE_SERVER_DIR,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def verify_all_healthy(
    brokers: list[str], attempts: int = 20, delay_seconds: float = 1.5
) -> dict[str, bool]:
    """Polls the real /api/status endpoint rather than trusting that a
    token exchange not raising means it works end to end — checks every
    broker in `brokers` per poll, so refreshing several tokens at once
    (login.py) doesn't take one full sequential window per broker.

    Keeps polling through healthy=false rather than giving up on the first
    response: a stale pre-restart ApiCallLog row is still the "most
    recent" row until the first post-restart sync tick completes and logs
    a new one, so an early return here previously produced a real false
    negative (found live, task: indmoney-totp-login) — fixed once, here,
    instead of separately in every script that needs this."""
    url = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/api/status"
    result = {b: False for b in brokers}
    for _ in range(attempts):
        time.sleep(delay_seconds)
        try:
            response = httpx.get(url, timeout=5)
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        by_broker = {b["broker"]: b for b in response.json()["brokers"]}
        for broker in brokers:
            status = by_broker.get(broker)
            if status is not None and status["healthy"]:
                result[broker] = True
        if all(result.values()):
            return result
    return result


def verify_broker_healthy(broker: str, attempts: int = 20, delay_seconds: float = 1.5) -> bool:
    return verify_all_healthy([broker], attempts=attempts, delay_seconds=delay_seconds)[broker]
