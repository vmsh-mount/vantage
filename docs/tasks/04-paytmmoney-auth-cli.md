# 04 — PaytmMoney Auth CLI

**Depends on:** 03
**Unlocks:** live PaytmMoney data (task 3's client needs a valid access token to do
anything real)

## Goal

A one-command way to (re-)generate the PaytmMoney access token, since the auth flow is
a manual browser login with no refresh token (see planning.md Research Findings).

## Scope

`bridge-server/scripts/paytmmoney_login.py` — interactive CLI:
1. Builds and prints the login URL from `PAYTMMONEY_API_KEY`.
2. User logs in in a browser (password + OTP), gets redirected with a `request_token`
   in the URL.
3. Script prompts for that pasted `request_token`.
4. Exchanges it for an access token via `generate_session()`.
5. Writes the resulting token into `.env` (`PAYTMMONEY_ACCESS_TOKEN=...`), replacing
   any existing value.

**Status: DONE, verified end-to-end 2026-07-19** with a real login (browser + OTP,
genuinely required a human — couldn't be automated or tested by me directly). Confirmed
from the same SDK source used in task 3
([pyPMClient](https://github.com/paytmmoney/pyPMClient)), not guessed:
- Login URL: `https://login.paytmmoney.com/merchant-login?apiKey={api_key}&state={state}`
- Token exchange: `POST https://developer.paytmmoney.com/accounts/v2/gettoken` with
  JSON body `{api_key, api_secret_key, request_token}` — note the body key is
  `api_secret_key`, not `api_secret`, easy to get wrong by assumption.
- `api_key` is not treated as a secret by this flow — it's embedded directly in the
  login URL, meant to be opened in a browser. `api_secret` and the resulting access
  token are the actual sensitive values and never appear in any script output.

**Two real bugs found on the first live run, both fixed:**
1. **The redirect's query param is `requestToken` (camelCase), not `request_token`.**
   Neither the SDK source nor any doc confirmed this — only observed from an actual
   redirect (`http://localhost:5000/callback?success=true&requestToken=...&state=...`).
   The registered redirect URI pointing at `localhost` with nothing listening there
   (giving a browser error page) is expected and harmless — the token is in the URL
   bar regardless of whether the page itself loads.
2. **The script didn't parse pasted input at all**, so pasting anything other than the
   bare token (e.g. the trailing `&state=...` along with it) got sent verbatim and
   correctly rejected by PaytmMoney's server as malformed (`400 Bad Request`). Fixed
   with `extract_request_token()`, which now accepts a bare token, a full redirect
   URL, or a query-string fragment (with or without a leading `requestToken=` key) and
   extracts the clean value regardless. Verified against the exact real inputs from
   this session, including the malformed paste that originally failed.

The already-issued token was re-exchanged successfully after the fix (no need to
redo the OTP flow) — 400 was purely from the malformed input, not an invalid/expired
token. `PAYTMMONEY_ACCESS_TOKEN` is live in `.env`.

## Out of scope

- No automatic/scheduled token refresh — this is a manual script, run when the token
  expires (surfaced by task 12's status endpoint).
- No INDmoney equivalent needed here — that token comes from the INDmoney dashboard
  directly, not a script.

## Acceptance criteria

- Running the script end-to-end with real credentials results in a working
  `PAYTMMONEY_ACCESS_TOKEN` in `.env` that task 3's `paytmmoney.py` client can
  successfully use. **✅ Verified** — `fetch_holdings()` returned 23 real holdings
  using the token this script wrote.
- Re-running it cleanly replaces the old token rather than duplicating the `.env` line.
  **✅ Verified** via the `.env`-rewrite tests (replace/re-run/append-if-missing).
- Observe and document the actual token validity window here once seen in practice
  (open question from planning.md) — **partially answered.** The token generated
  during this task's real login stayed valid through tasks 5, 6, and 7's real-data
  checks, then returned a real `401 Unauthorized` during task 8's — so it expired
  sometime within that window, consistent with planning.md's Kite-Connect-style daily
  expiry expectation. Exact hours-to-live still unmeasured (no precise timestamps were
  recorded at generation or failure time), but same-day expiry is now empirically
  confirmed, not just assumed from Zerodha's pattern. `run_sync_pipeline` handled the
  failure exactly as task 5 designed: logged it, didn't crash, other holdings (the mock
  INDmoney one) kept syncing normally — a live confirmation of that task's own
  acceptance criteria, not just the synthetic in-process test that originally verified
  it. Re-running `make login` regenerates it.
