"""Automates INDstocks REST token regeneration (docs/tasks/indmoney-totp-login.md)
— the daily-expiring token used by the Phase-1 scheduler's INDmoney holdings
sync, separate from task 24's INDmoney MCP OAuth client.

Uses a TOTP code computed locally from a stored shared secret (the same
primitive an authenticator app implements — pyotp, not a novel approach),
exactly like PaytmMoney's login script uses a one-time interactive browser
step instead of storing a password. The account MPIN required by
INDstocks' /generate/token endpoint is deliberately NEVER stored: prompted
via getpass() each run, used exactly once in the request body, never
written to .env, logs, or the DB — see the task doc for why (a real account
credential, not a derived/revocable one, and explicitly out of scope per
planning-phase2.md §9)."""

import getpass
import sys
from pathlib import Path

import httpx
import pyotp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from scripts._bridge_control import (  # noqa: E402
    LOG_PATH,
    restart_bridge_server,
    verify_broker_healthy,
    write_env_var,
)

TOKEN_URL = "https://api.indstocks.com/generate/token"


def generate_totp_code() -> str:
    if not settings.indmoney_totp_setup_key:
        raise SystemExit(
            "INDMONEY_TOTP_SETUP_KEY is blank in .env — set it up once at "
            "indstocks.com/app/api-trading/access-tokens (Setup TOTP), then paste the "
            "setup key shown there (only shown once) into .env."
        )
    return pyotp.TOTP(settings.indmoney_totp_setup_key).now()


def exchange_for_token(mpin: str, totp_code: str) -> str:
    if not settings.indmoney_client_id:
        raise SystemExit("INDMONEY_CLIENT_ID is blank in .env — see the TOTP setup page for it.")
    response = httpx.post(
        TOKEN_URL,
        json={"mpin": mpin, "totp": totp_code},
        headers={"x-api-key": settings.indmoney_client_id, "Content-Type": "application/json"},
        timeout=15,
    )
    if response.status_code != 200:
        # INDstocks locks out after repeated failures (5 in a row -> 15min,
        # 3 lockouts/hour -> 1h) — surface the real response body rather
        # than a bare status code, since "wrong MPIN" vs "locked out" vs
        # "rate limited (1 req/60s)" need different next steps from the user.
        raise SystemExit(f"Token request failed ({response.status_code}): {response.text}")
    payload = response.json()
    if "token" not in payload:
        raise SystemExit(f"No 'token' in response: {payload}")
    return payload["token"]


def perform_login() -> None:
    """The TOTP + MPIN exchange + .env write, without restarting/verifying
    — factored out so scripts/login.py can run this back-to-back with
    PaytmMoney's own perform_login() and only restart/verify once at the
    end, instead of once per broker."""
    totp_code = generate_totp_code()
    print(f"Computed TOTP code from your stored setup key: {totp_code}")

    mpin = getpass.getpass("Enter your INDmoney account MPIN (not stored, used once): ")
    if not mpin:
        raise SystemExit("No MPIN entered, aborting.")

    print("\nExchanging MPIN + TOTP for an access token...")
    access_token = exchange_for_token(mpin, totp_code)
    del mpin  # out of scope immediately after use — nothing else references it

    write_env_var("INDMONEY_ACCESS_TOKEN", access_token)
    print("INDMONEY_ACCESS_TOKEN written to .env")


def main() -> None:
    perform_login()

    print(f"\nRestarting bridge-server (logs: {LOG_PATH})...")
    restart_bridge_server()

    print("Verifying against a real /api/status call...")
    if verify_broker_healthy("indmoney"):
        print("INDmoney is healthy.")
    else:
        print(
            "INDmoney still isn't showing healthy after the restart — check "
            f"{LOG_PATH} for the real error (a fresh token can still fail if the account "
            "needs re-KYC, or if INDstocks' own API is degraded)."
        )


if __name__ == "__main__":
    main()
