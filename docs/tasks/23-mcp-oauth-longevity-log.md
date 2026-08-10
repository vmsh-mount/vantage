# INDmoney MCP OAuth Longevity Log

Tracks how long the INDmoney MCP's OAuth grant actually survives before re-consent is needed —
per task 23 (planning-phase2.md §3: "auto-rotates and *may* need re-consent only occasionally —
unmeasured"). This can't be answered in one sitting; it only emerges from calendar time passing
while the connection is used normally. Add a new dated row whenever connectivity is checked
(success or failure) — this file just accumulates data points until a real pattern is visible.

**Current status: substantially answered by task 24, for bridge-server's own client identity.**
The access token itself is short-lived (`expires_in: 3600`, i.e. 1 hour) — but the **refresh
token survived a 2+ hour gap and successfully minted a new access token with zero browser
interaction.** The earlier-looking "requires re-consent every run" behavior recorded below
(2026-07-24 row) was a **bug in bridge-server's own client, not an INDmoney limitation**: the
official `mcp` SDK's token-expiry tracking is purely in-memory and never restored from
persisted storage, so a fresh process couldn't tell a loaded token was stale and skipped
straight past the SDK's (working) proactive-refresh path into a full interactive reauth. Fixed
in `FileTokenStorage` (bridge-server's own issued-at tracking); confirmed fixed same day. See
the 2026-07-24 rows below for the full sequence. **Still open:** how long the *refresh token
itself* lasts before INDmoney requires fresh consent — 2+ hours confirmed, true ceiling
unknown, keep logging.

**Open item:** INDmoney's own site may show a "connected apps" / authorized third-party access
page with the grant's actual creation date — if so, backfilling that here would give a real
start date instead of "first observed working on X." Worth checking (same pattern as the
PaytmMoney token-portal screenshot used earlier in this project) next time this file is updated.

## Log

| Date | Check | Result | Notes |
|---|---|---|---|
| 2026-07-23 | `lookup_ind_keys(["RELIANCE"])` via the connected (interactive Claude Code session's) MCP connection | ✅ Reachable, no re-consent prompt | First recorded data point. A *different* client identity from bridge-server's own (below) — Claude's own session connection, unrelated to this codebase. |
| 2026-07-23 | `scripts/indmoney_mcp_login.py` — bridge-server's own first-ever consent | ✅ Real browser consent completed (user's own mobile/OTP/MPIN), `networth_snapshot` succeeded immediately after | bridge-server's own client identity established. `expires_in` on the issued access token: 3600s (1 hour). Refresh token issued too. |
| 2026-07-24 | `scripts/indmoney_mcp_smoke_test.py`, independent process, tokens loaded from disk | ❌ Fell through to full interactive reauth | **Root-caused, not a real INDmoney limit**: the `mcp` SDK's expiry tracking (`OAuthContext.token_expiry_time`) is in-memory only, never restored from `TokenStorage` — a fresh process can't tell a loaded token is stale, sends it anyway, gets a real 401, and the SDK's 401-handling path goes straight to full reauth rather than trying the refresh token first. |
| 2026-07-24 | Fixed `FileTokenStorage` to track `tokens_issued_at` itself and blank a likely-stale `access_token` on load (routes through the SDK's *working* proactive-refresh path instead) | ✅ Fix implemented | See `app/integrations/indmoney_mcp.py` — `FileTokenStorage` docstring has the full root-cause writeup. |
| 2026-07-24 | Smoke test re-run with `tokens_issued_at` artificially backdated 2 hours (same real refresh token, no new consent) | ✅ **Silent proactive refresh succeeded — zero browser interaction.** New `access_token` confirmed issued (`tokens_issued_at` updated to ~now), all 3 real MCP calls succeeded | **The actual headline finding**: bridge-server's refresh token survived a 2+ hour gap and self-renewed correctly once the client-side bug was fixed. Re-consent is not needed anywhere near as often as tasks 23/24's cautious framing assumed — the earlier pessimism was about an unmeasured *client* limitation, not a real INDmoney constraint. True refresh-token ceiling still unknown (only 2+ hours confirmed so far) — keep logging as more real time passes. |
