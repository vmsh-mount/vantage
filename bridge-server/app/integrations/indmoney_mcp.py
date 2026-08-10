"""bridge-server as its own INDmoney MCP/OAuth client — task 24
(planning-phase2.md §4). A separate client identity from whatever
connection any interactive Claude Code session already has to INDmoney's
MCP; this one is bridge-server's, persisted across process restarts.

Uses the official `mcp` SDK's streamable-http transport and its OAuth 2.1 +
PKCE + Dynamic Client Registration implementation (OAuthClientProvider) —
not a from-scratch OAuth build. DCR means no pre-registration on INDmoney's
side is needed, unlike PaytmMoney's fixed api_key/redirect_uri model.

Hard boundary, restated from task 23: this module never sees or requests
the user's mobile/OTP/MPIN. Browser consent is always the user's own,
completed on INDmoney's own page."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.auth.oauth2 import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

INDMONEY_MCP_URL = "https://mcp.indmoney.com/mcp"
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 8765
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}/callback"

BRIDGE_SERVER_DIR = Path(__file__).resolve().parent.parent.parent
TOKEN_STORE_PATH = BRIDGE_SERVER_DIR / ".indmoney_mcp_tokens.json"


class FileTokenStorage(TokenStorage):
    """Persists both the OAuth tokens and the Dynamic-Client-Registration
    client_id/secret to one local file — both must survive process
    restarts, or every run would need a fresh consent. Functionally a
    credential: chmod 600, gitignored (see task 24 acceptance criteria).

    Verified live (task 24): the SDK's own OAuthContext.token_expiry_time
    is a plain in-memory field, only ever set when tokens are freshly
    obtained *this process* (mcp/client/auth/oauth2.py's
    update_token_expiry, called from _handle_token_response /
    _handle_refresh_response) — it is never restored from TokenStorage. A
    fresh process loading a token via get_tokens() therefore has no way to
    know it's stale, is_token_valid() defaults to True, the stale token
    gets sent, the server 401s, and — confirmed by reading
    async_auth_flow — the 401-handling branch does NOT retry via
    refresh_token, it goes straight to full interactive reauth. Confirmed
    end-to-end: a token good for 1 hour required a fresh browser consent
    on the very next independent process run.

    Fix, entirely within this class, no SDK internals touched: track
    tokens_issued_at ourselves, and on get_tokens(), if enough time has
    passed that the access token is likely expired, hand back the token
    with access_token blanked (but refresh_token intact). That alone
    makes is_token_valid() correctly False and can_refresh_token() True,
    which routes through the SDK's *proactive* pre-request refresh path
    (the one that actually works) instead of ever reaching the broken
    401 path."""

    REFRESH_SAFETY_MARGIN_SECONDS = 60

    def __init__(self, path: Path = TOKEN_STORE_PATH):
        self.path = path

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))
        self.path.chmod(0o600)

    async def get_tokens(self) -> OAuthToken | None:
        data = self._read()
        token_data = data.get("tokens")
        if not token_data:
            return None
        token = OAuthToken.model_validate(token_data)

        issued_at = data.get("tokens_issued_at")
        if issued_at is not None and token.expires_in is not None:
            likely_expired = time.time() >= issued_at + token.expires_in - self.REFRESH_SAFETY_MARGIN_SECONDS
            if likely_expired:
                token = token.model_copy(update={"access_token": ""})
        return token

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        data["tokens_issued_at"] = time.time()
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(data) if data else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
        self._write(data)


async def _default_redirect_handler(url: str) -> None:
    """Overridden by scripts/indmoney_mcp_login.py's interactive flow (which
    also opens the browser); this default just makes the URL impossible to
    miss if something calls the provider without supplying its own
    handler — it deliberately does not open a browser or block on input,
    since bridge-server itself must never require interactive consent
    mid-request."""
    print(f"INDmoney MCP authorization required — visit: {url}")


async def _unattended_callback_handler() -> tuple[str, str | None]:
    raise RuntimeError(
        "INDmoney MCP requires interactive re-consent and no callback handler was "
        "supplied — run scripts/indmoney_mcp_login.py to reauthorize."
    )


def build_oauth_provider(
    storage: TokenStorage | None = None,
    redirect_handler=None,
    callback_handler=None,
) -> OAuthClientProvider:
    return OAuthClientProvider(
        server_url=INDMONEY_MCP_URL,
        client_metadata=OAuthClientMetadata(
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            client_name="Vantage bridge-server",
        ),
        storage=storage or FileTokenStorage(),
        redirect_handler=redirect_handler or _default_redirect_handler,
        callback_handler=callback_handler or _unattended_callback_handler,
    )


class RateLimitExceeded(RuntimeError):
    """Raised when INDmoney's MCP server returns its rate-limit error
    envelope (verified live, task 25: {"error": "rate_limit_exceeded",
    "retry_after_seconds": N, ...}) instead of tool data. Without this
    check the error dict was silently handed to callers as if it were a
    real result — e.g. lookup_ind_keys callers doing matches[0] on it
    raised a confusing KeyError: 0 instead of a clear rate-limit signal."""

    def __init__(self, retry_after_seconds: float, message: str):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


def _raise_if_rate_limited(parsed: Any) -> Any:
    if isinstance(parsed, dict) and parsed.get("error") == "rate_limit_exceeded":
        raise RateLimitExceeded(
            retry_after_seconds=parsed.get("retry_after_seconds", 60),
            message=parsed.get("message", "INDmoney MCP rate limit exceeded"),
        )
    return parsed


def _unwrap_double_encoded(parsed: Any) -> Any:
    """Verified live (task 24): INDmoney's MCP tools double-encode — both
    structuredContent *and* the text content block come back as
    {"result": "<json string>"}, a dict with one key whose value is
    *another* JSON string holding the actual structured data. Confirmed
    directly: structuredContent for lookup_ind_keys was
    {'result': '[...]'} while the correctly-shaped list was sitting one
    decode further in. Unwrap that specific shape; anything else passes
    through unchanged."""
    if isinstance(parsed, dict) and set(parsed) == {"result"} and isinstance(parsed["result"], str):
        try:
            return json.loads(parsed["result"])
        except json.JSONDecodeError:
            return parsed["result"]
    return parsed


def _extract_result(result) -> Any:
    """CallToolResult carries either structuredContent (a dict, when the
    server supports it) or a list of content blocks whose text is a JSON
    string — handle both, and unwrap either the same way."""
    if result.isError:
        text = "; ".join(getattr(block, "text", str(block)) for block in result.content)
        raise RuntimeError(f"INDmoney MCP tool call failed: {text}")
    if result.structuredContent is not None:
        return _raise_if_rate_limited(_unwrap_double_encoded(result.structuredContent))
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return text
            return _raise_if_rate_limited(_unwrap_double_encoded(parsed))
    return None


RATE_LIMIT_MAX_RETRIES = 3
RATE_LIMIT_RETRY_BUFFER_SECONDS = 2


def _first_rate_limit_error(exc: BaseException) -> "RateLimitExceeded | None":
    """`except* RateLimitExceeded` still hands back a BaseExceptionGroup, not
    a bare RateLimitExceeded — streamablehttp_client and ClientSession each
    run their own anyio TaskGroup, so the real exception is nested two
    groups deep. Walk down to the actual instance to read retry_after_seconds."""
    if isinstance(exc, RateLimitExceeded):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _first_rate_limit_error(sub)
            if found is not None:
                return found
    return None


async def call_tool(name: str, arguments: dict[str, Any] | None = None, oauth_provider: OAuthClientProvider | None = None) -> Any:
    """Opens a fresh session per call — simplest correct thing for task
    24's connectivity layer; task 25+ can add session reuse if the
    connect-per-call overhead actually matters once this is on a live
    request path.

    Verified live (task 25): INDmoney's MCP enforces a real global
    rate limit (30 calls/min as observed) that a single volatility-stops
    request can exceed on its own (2 calls per holding). Retries honor
    the server's own retry_after_seconds rather than guessing a backoff.

    RateLimitExceeded is raised from inside the two nested `async with`
    blocks below, so anyio's TaskGroup cleanup (used internally by
    streamablehttp_client) re-wraps it in a BaseExceptionGroup — the same
    ExceptionGroup-unwrapping quirk task 24 hit once already. `except*`
    walks nested groups by exception type regardless of depth, so it
    catches this reliably instead of needing a plain `except`."""
    provider = oauth_provider or build_oauth_provider()
    for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
        try:
            async with streamablehttp_client(INDMONEY_MCP_URL, auth=provider) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments or {})
                    return _extract_result(result)
        except* RateLimitExceeded as eg:
            if attempt == RATE_LIMIT_MAX_RETRIES:
                raise
            rate_limit_exc = _first_rate_limit_error(eg)
            assert rate_limit_exc is not None
            await asyncio.sleep(rate_limit_exc.retry_after_seconds + RATE_LIMIT_RETRY_BUFFER_SECONDS)
    raise AssertionError("unreachable")  # loop always returns or raises
