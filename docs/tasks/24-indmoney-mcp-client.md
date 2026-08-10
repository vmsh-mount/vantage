# 24 — bridge-server as INDmoney MCP/OAuth Client

**Depends on:** 23 (token-refresh helper — established the "no OTP automation, ever" boundary
this task inherits; the MCP longevity log this task's consent flow feeds)
**Unlocks:** 25 (deterministic fact tools — vol-scaled stops/benchmark need bridge-server to
fetch OHLC itself, which is exactly what this task builds)

## Goal

§4 of planning-phase2.md identified a real architectural hole in the v1 plan: an MCP *server*
cannot be a client of another MCP server, so "Python fact tools computing from OHLC pulled via
the INDmoney MCP" was impossible as originally drawn. The fix decided there: **bridge-server
becomes its own INDmoney MCP/OAuth client** — a separate, first-class client identity from
whatever connection this Claude Code session already has to INDmoney's MCP (that connection is
Claude's own, unrelated to this codebase; bridge-server needs its own).

## Scope

**Library choice**: the official `mcp` Python SDK (`pip install mcp`, installed and verified —
v1.28.1) ships a working streamable-http client (`mcp.client.streamable_http`) *and* a full
OAuth 2.1 + PKCE + Dynamic Client Registration implementation
(`mcp.client.auth.oauth2.OAuthClientProvider`, an `httpx.Auth`). No new dependency needed beyond
`mcp` itself — this is the reference implementation, not a from-scratch OAuth build.

**`bridge-server/app/integrations/indmoney_mcp.py`** — the persistent client:
- `FileTokenStorage` implementing the SDK's `TokenStorage` protocol (`get_tokens`/`set_tokens`/
  `get_client_info`/`set_client_info`), persisting to `bridge-server/.indmoney_mcp_tokens.json`
  — both the OAuth access/refresh tokens *and* the Dynamic-Client-Registration `client_id`/
  `client_secret`, since both must survive across process restarts. `chmod 600`, gitignored —
  same protection as `.env`, since this file is functionally a credential.
- An `OAuthClientProvider` configured against `https://mcp.indmoney.com/mcp` with a local
  redirect URI (DCR means no pre-registration on INDmoney's side is needed, unlike PaytmMoney's
  fixed api_key/redirect_uri model — task 4's flow doesn't apply here).
- An async `call_tool(name, arguments) -> dict` wrapper that opens a `ClientSession` via
  `streamablehttp_client(url, auth=oauth_provider)`, initializes, calls the named tool, and
  returns the parsed result — callable from sync code via `asyncio.run(...)` until task 25/28
  bring real async request paths into bridge-server.

**`scripts/indmoney_mcp_login.py`** — the one-time interactive consent flow (mirrors
`paytmmoney_login.py`'s shape, different mechanics): spins up a short-lived local HTTP server on
the redirect URI's port to catch the `?code=&state=` callback, opens the browser
(`webbrowser.open`) to the authorization URL, waits for the callback, lets `OAuthClientProvider`
complete the token exchange (tokens land in `FileTokenStorage` automatically), then calls
`list_tools()` as an immediate real-world confirmation it actually works. **Requires the user to
complete the browser consent (mobile + OTP + MPIN) themselves on INDmoney's own page** — same
hard boundary as task 23, restated because it's a new codepath: this script never sees or
requests those credentials.

**`scripts/indmoney_mcp_smoke_test.py`** — the contract smoke-test, using tool shapes verified
live in this session (not guessed):
- `lookup_ind_keys(["RELIANCE"])` → asserts a list of dicts, each with `ind_key` and `name`.
- `networth_snapshot()` → asserts a dict with a numeric `total_networth` and a list
  `investments`.
- `get_indian_stocks_ohlc(ind_key=..., interval="1day", lookback="7d")` → asserts a dict with a
  list `candles`, each candle carrying `close` and `datetime_ist`.

If any of these shapes drift, the smoke-test fails loudly and specifically (which field, which
tool) rather than task 25's fact tools silently computing wrong numbers from a shape mismatch.

## Out of scope

- No wiring into any live FastAPI endpoint yet — task 25 is where this client's data starts
  powering actual dashboard/fact-tool features. Task 24 is the connectivity layer only.
- No async migration of existing sync routes — the client is self-contained async, invoked via
  `asyncio.run(...)` from sync callers for now.
- No handling of INDmoney MCP write/order tools — none exist in the connected tool set (verified
  task 20), so there's nothing to explicitly exclude from the allowlist yet; that enforcement
  becomes concrete once task 28's agent allowlist exists.

## Acceptance criteria

- Running `scripts/indmoney_mcp_login.py` end to end, with the user completing a real browser
  consent (their own mobile/OTP/MPIN, never entered anywhere in this codebase), results in a
  populated, `chmod 600`, gitignored `.indmoney_mcp_tokens.json` and a successful `list_tools()`
  printout — verified against the real INDmoney MCP, not mocked.
- `scripts/indmoney_mcp_smoke_test.py` run afterward, using the persisted tokens with **no
  further browser interaction**, succeeds against all three tools and prints real returned data
  (confirming token *reuse*, not just initial consent, works).
- Killing and re-running the smoke test a second time still works with no re-consent — the
  first concrete data point for task 23's still-open MCP longevity log, recorded there once
  observed.
- `.indmoney_mcp_tokens.json` never appears in `git status` as untracked-and-about-to-be-added —
  confirmed via `.gitignore`.
