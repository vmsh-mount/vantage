import secrets
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from scripts._bridge_control import (  # noqa: E402
    LOG_PATH,
    restart_bridge_server,
    verify_broker_healthy,
    write_env_var,
)

LOGIN_URL = "https://login.paytmmoney.com/merchant-login"
TOKEN_URL = "https://developer.paytmmoney.com/accounts/v2/gettoken"


def build_login_url() -> str:
    state = secrets.token_hex(8)
    return f"{LOGIN_URL}?apiKey={settings.paytmmoney_api_key}&state={state}"


def extract_request_token(raw: str) -> str:
    """Accepts a bare token, a full redirect URL, or just the query-string
    tail (with or without a leading key=), and returns just the token value.
    The redirect param has been observed as 'requestToken' (camelCase) in
    practice, not 'request_token' as PaytmMoney's own docs/SDK would suggest
    — this parser checks both rather than assuming one."""
    raw = raw.strip()

    if "://" in raw:
        query = urlparse(raw).query
    elif "=" in raw:
        query = raw
    else:
        return raw  # bare token, nothing to parse

    params = parse_qs(query)
    for key in ("requestToken", "request_token"):
        if params.get(key):
            return params[key][0]

    # Pasted starting mid-value, e.g. "TOKEN&state=...", with no leading
    # "requestToken=" — the first '&'-delimited chunk with no '=' in it is
    # the token itself.
    first_chunk = raw.split("&", 1)[0]
    if "=" not in first_chunk:
        return first_chunk

    return raw  # nothing recognizable matched; let the API's error surface


def exchange_request_token(request_token: str) -> str:
    response = httpx.post(
        TOKEN_URL,
        json={
            "api_key": settings.paytmmoney_api_key,
            "api_secret_key": settings.paytmmoney_api_secret,
            "request_token": request_token,
        },
        headers={"Content-Type": "application/json", "openapi-client-src": "sdk"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if "access_token" not in payload:
        raise ValueError(f"No access_token in response: {payload}")
    return payload["access_token"]


def perform_login() -> None:
    """The interactive exchange + .env write, without restarting/verifying
    — factored out so scripts/login.py can run this back-to-back with
    INDmoney's own perform_login() and only restart/verify once at the end,
    instead of once per broker."""
    url = build_login_url()
    print("Opening the PaytmMoney login page in your browser — log in (password + OTP):\n")
    print(url)
    webbrowser.open(url)
    print(
        "\nAfter login you'll be redirected to your app's registered redirect URI. "
        "The page may show an error (expected if nothing runs on that address) — "
        "that's fine, ignore it. Paste the FULL URL from the browser's address bar "
        "below; the token gets extracted automatically regardless of exactly what "
        "you paste (full URL, just the query string, or the bare token)."
    )
    raw_input_value = input("\nPaste the redirect URL (or just the token): ").strip()
    request_token = extract_request_token(raw_input_value)

    print("\nExchanging request_token for an access token...")
    access_token = exchange_request_token(request_token)

    write_env_var("PAYTMMONEY_ACCESS_TOKEN", access_token)
    print("PAYTMMONEY_ACCESS_TOKEN written to .env")


def main() -> None:
    perform_login()

    print(f"\nRestarting bridge-server (logs: {LOG_PATH})...")
    restart_bridge_server()

    print("Verifying against a real GET /api/status call...")
    if verify_broker_healthy("paytmmoney"):
        print("\n✅ PaytmMoney is live and healthy.")
    else:
        print(
            "\n⚠️  bridge-server restarted, but /api/status didn't report PaytmMoney as "
            f"healthy. Check {LOG_PATH} for what actually happened — the token exchange "
            "succeeding doesn't guarantee the new token works end to end."
        )


if __name__ == "__main__":
    main()
