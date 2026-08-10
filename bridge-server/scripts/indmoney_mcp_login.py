"""One-time interactive consent flow for bridge-server's own INDmoney MCP
OAuth client identity (task 24) — mirrors paytmmoney_login.py's shape,
different mechanics (OAuth 2.1 + PKCE + Dynamic Client Registration via the
official mcp SDK, not a fixed api_key exchange).

Hard boundary: this script never sees or requests the user's mobile, OTP,
or MPIN. All of that happens on INDmoney's own page in the browser; this
process only ever receives the final authorization code via the local
redirect callback below.
"""

import asyncio
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations.indmoney_mcp import (  # noqa: E402
    REDIRECT_HOST,
    REDIRECT_PORT,
    TOKEN_STORE_PATH,
    build_oauth_provider,
    call_tool,
)


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming convention
        query = parse_qs(urlparse(self.path).query)
        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        error = query.get("error_description", query.get("error", [None]))[0]
        self.server.result = (code, state, error)  # type: ignore[attr-defined]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if code:
            self.wfile.write(b"<html><body>Authorized \xe2\x80\x94 you can close this tab and return to the terminal.</body></html>")
        else:
            self.wfile.write(f"<html><body>Authorization failed: {error}</body></html>".encode())

    def log_message(self, format_str: str, *args) -> None:
        pass  # suppress BaseHTTPRequestHandler's default per-request stderr logging


async def main() -> None:
    # Bound synchronously here, before the browser is ever opened, so
    # there's no window where the redirect could arrive before something
    # is listening for it.
    server = HTTPServer((REDIRECT_HOST, REDIRECT_PORT), _CallbackHandler)
    server.result = None  # type: ignore[attr-defined]

    async def wait_for_callback() -> tuple[str, str | None]:
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        while server.result is None:  # type: ignore[attr-defined]
            await asyncio.sleep(0.2)
        thread.join(timeout=5)
        code, state, error = server.result  # type: ignore[attr-defined]
        if error or not code:
            raise RuntimeError(f"INDmoney authorization failed: {error or 'no code returned'}")
        return code, state

    async def redirect_handler(url: str) -> None:
        print(f"\nOpening the INDmoney authorization page in your browser:\n{url}\n")
        print("Log in with your mobile, OTP, and MPIN on INDmoney's own page — this ")
        print("script never sees any of that; it only receives the redirect afterward.\n")
        webbrowser.open(url)

    provider = build_oauth_provider(redirect_handler=redirect_handler, callback_handler=wait_for_callback)

    print("Starting INDmoney MCP authorization for bridge-server...")
    try:
        result = await call_tool("networth_snapshot", oauth_provider=provider)
    finally:
        server.server_close()

    print(f"\n✅ Connected. Tokens written to {TOKEN_STORE_PATH}.")
    print("Sample response (networth_snapshot, truncated):")
    print(json.dumps(result, indent=2)[:500])


if __name__ == "__main__":
    asyncio.run(main())
