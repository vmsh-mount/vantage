# INDmoney REST Token Automation (TOTP-Based Login)

**Context:** the INDstocks REST API (`api.indstocks.com`, the Phase-1 `IndmoneyClient` used by the
scheduler's holdings sync — separate from task 24's INDmoney *MCP* client) has always required
manually regenerating `INDMONEY_ACCESS_TOKEN` at indstocks.com when it expires daily. Not a
numbered Phase 2 task — a direct follow-up requested after the user obtained a Client ID and TOTP
setup key from INDstocks' API dashboard, asking to automate it "just like PaytmMoney."

## Real findings, researched live before writing any code

- INDstocks' actual token-generation flow (`api-docs.indstocks.com/Users/`, confirmed via direct
  fetch): `POST https://api.indstocks.com/generate/token`, header `x-api-key: <Client ID>`, body
  `{"mpin": "...", "totp": "..."}` → `{"token": "..."}`. Token valid **24h**; generating a new one
  **invalidates the previous one**; **1 request per 60s minimum**; 5 failed attempts locks out
  15 minutes, 3 lockouts in an hour locks out 1 hour.
- The **Client ID + TOTP setup key** pair is fundamentally different from PaytmMoney's
  `api_key`/`api_secret`: the setup key is a TOTP shared secret (same mechanism an authenticator
  app uses) — a valid 6-digit code can be computed locally from it and the current time, with no
  interactive step, unlike SMS OTP. That part is genuinely, safely automatable.
- **The endpoint also requires the account MPIN** — a real trading PIN, not a derived/expiring
  value. This is a materially different secret than anything else this project stores: `.env`
  already holds `PAYTMMONEY_API_KEY`/`_SECRET` and the INDmoney MCP OAuth token, but none of
  those are, by themselves, sufficient to authorize account actions the way an MPIN is.
  Planning-phase2.md §9 explicitly lists as a non-goal: *"No unattended automation that requires
  handling your OTP or storing broker login credentials."*

## Decision (asked, not assumed)

Presented the tradeoff directly rather than picking a default: store the MPIN too (fully silent,
one-command automation) vs. store only the TOTP setup key and prompt for MPIN interactively each
run (no silent storage of a live account credential, but still requires a manual command
periodically — the same shape as `paytmmoney_login.py` already has, which likewise requires an
interactive browser login step each time rather than storing a password). **User chose the
latter.**

## What this adds

- `app/config.py`: `indmoney_client_id`, `indmoney_totp_setup_key` (both blank by default — no
  effect on a fresh checkout).
- `bridge-server/scripts/indmoney_login.py` (new) — mirrors `paytmmoney_login.py`'s shape:
  computes the current TOTP code from the stored setup key (`pyotp`), prompts for MPIN via
  `getpass` (never echoed, never written to disk or logs), calls `/generate/token`, writes the
  returned token to `INDMONEY_ACCESS_TOKEN` in `.env`, restarts bridge-server, and polls
  `/api/status` to confirm the token actually works end-to-end — not just that the exchange call
  didn't raise.
- `.env.example`, `Makefile` (`make indmoney-login`) updated to match.
- `requirements.txt`: `pyotp` (MIT-licensed, the standard Python TOTP library — same primitive
  every authenticator app implements, not a novel/unvetted approach).

## Out of scope

- No storage of the MPIN, anywhere, ever — confirmed by inspection: `getpass.getpass()`'s return
  value is used exactly once (in the request body) and never assigned to anything written to
  `.env`, logs, or the DB.
- No scheduler-driven automatic regeneration — the 60s-between-requests and lockout-on-failure
  rules make an unattended retry loop actively risky (a bug that retries too aggressively could
  lock the account out for an hour), and it would require exactly the MPIN-storage tradeoff just
  declined. This stays a manual, user-run command, same as PaytmMoney's.

## Acceptance criteria

- A real TOTP code computed from the stored setup key is accepted by `/generate/token` — proven
  live, not assumed from `pyotp`'s own correctness. **Verified**: the user ran `make
  indmoney-login` for real, entered their real MPIN, and the exchange succeeded first try.
- The MPIN is never persisted — confirmed by inspection of the script and by checking `.env`
  after a run contains no MPIN-shaped field. **Verified**: `.env` after the run contains only
  `INDMONEY_ACCESS_TOKEN=<token>`, no MPIN anywhere.
- `/api/status` shows INDmoney `healthy: true` after running the script, and a real
  `/api/refresh` afterward successfully pulls real INDmoney holdings (not just "the token exchange
  returned 200"). **Verified, after finding and fixing a real bug in the verification itself**:
  the script initially reported "INDmoney still isn't showing healthy" even though the token
  exchange had genuinely succeeded — `verify_indmoney_healthy()` returned on the *first*
  `/api/status` response regardless of its `healthy` value, so a stale pre-restart `ApiCallLog`
  row (the "most recent" row until the first post-restart sync tick completes and logs a new
  one) read as a real failure. A direct `curl /api/status` immediately after confirmed
  `healthy: true` with a fresh `last_sync_at` — the fix (only return early on `healthy: true`,
  keep polling through `false`, widen the window to 20×1.5s) was verified against the
  already-healthy live server. Applied the identical fix to `paytmmoney_login.py`'s sibling
  function, which had the same latent bug (hadn't surfaced there in practice, but is the same
  race).
