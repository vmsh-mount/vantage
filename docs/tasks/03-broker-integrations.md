# 03 — Broker Integration Layer

**Depends on:** 01, 02
**Unlocks:** 04, 05

## Goal

The swappable contract every broker client implements, plus PaytmMoney (live) and
INDmoney (mock) behind it. This is the only layer allowed to make outbound broker HTTP
calls.

## Scope

**Do this first, before writing any parsing code**: make one real authenticated call to
PaytmMoney's holdings endpoint (credentials already exist) and dump the raw JSON.
Confirm whether `close_price` (or an equivalent previous-close field) is actually
present — the docs site couldn't be verified reliably (see planning.md Gaps) and
`Holding.close_price` (task 2) is nullable specifically because of this uncertainty.
Record the actual field name/absence in this file once known. Same check for INDmoney
once real credentials exist, opportunistically — not blocking, since it ships mocked
either way.

**Status: RESOLVED 2026-07-19, verified against a real authenticated call** (23 real
holdings, via task 4's login flow). The endpoint/auth mechanism was already confirmed
from PaytmMoney's own SDK source
([pyPMClient](https://github.com/paytmmoney/pyPMClient)):
- Base host `https://developer.paytmmoney.com`, holdings path
  `/holdings/v1/get-user-holdings-data` (GET).
- Auth is a **custom `x-jwt-token` header**, not `Authorization: Bearer` — would have
  gotten this wrong by assumption.

The response *field names* — which the SDK's own tests never covered, only error
paths — turned out to differ from every guess in planning.md's docs-site research.
Real, verified names:
- Response envelope is `{"data": {"results": [...]}}`, not `{"data": [...]}`.
- `close_price` → **`pc`** (previous close). Confirmed beyond doubt: checked all 23
  holdings, every one shows a small, plausible daily move in both directions between
  `pc` and `last_traded_price`, present on every row without exception. This settles
  the open question from task 2/planning.md's Gaps — `close_price` is genuinely
  available from PaytmMoney.
- `avg_cost` → `cost_price` (not `avg_price`/`average_price` as guessed).
- `symbol` → `nse_symbol` (not `symbol`/`trading_symbol`).
- `isin` → `isin_code` (not `isin`).
- `exchange` is the literal string `"ALL"` (dual NSE/BSE-listed) on every row — not a
  usable per-holding value. Since PaytmMoney is an NSE/BSE-only broker by construction
  and `nse_symbol` is used as the canonical symbol, `paytmmoney.py` now hardcodes
  `exchange="NSE"` rather than parsing `"ALL"`.
- `market_value`, `pnl`, `pnl_percent` are still not directly provided — computed from
  `quantity`/`ltp`/`cost_price` as already designed, unchanged.

`paytmmoney.py` updated to use the verified names as primary candidates, with the
original guesses kept as lower-priority fallbacks (harmless, in case the shape varies
by holding/segment type — this portfolio is all plain equity). Re-ran
`PaytmMoneyClient().fetch_holdings()` end-to-end against the live API after the fix:
23/23 holdings parsed correctly, every `close_price` populated, no exceptions.

INDmoney's live path remains unverified (best-effort only, from a third-party
integration doc) — still explicitly "opportunistic, not blocking" per this task's own
scope, since it ships mocked regardless.

`bridge-server/app/integrations/base.py`
- `NormalizedHolding` — the unified shape: symbol, exchange, quantity, avg cost,
  current price, close price, market value, unrealized P&L, sector, asset class,
  currency.
- `BrokerClient` protocol — one method: `fetch_holdings() -> list[NormalizedHolding]`.

`bridge-server/app/integrations/sample_data.py`
- Realistic fixture `NormalizedHolding` lists, reusing the same holdings used in the UI
  prototype (RELIANCE, INFY, TCS, HDFCBANK, ICICIBANK, plus AAPL/MSFT as manual) so the
  mocked bridge and the UI mockup tell the same story.

`bridge-server/app/integrations/paytmmoney.py`
- httpx client calling the real Trading API (`user_holdings_data()` equivalent) using
  key/secret/access token from `.env`. Built live from day one — credentials exist.

`bridge-server/app/integrations/indmoney.py`
- Same `BrokerClient` protocol, returns `sample_data.py` fixtures while
  `INDMONEY_MODE=mock`. Live implementation stubbed but unused until credentials exist;
  switching later is a config change, not a code change.

`bridge-server/app/integrations/fx.py`
- Fetches USD/INR once per refresh cycle from a free rate API, caches in memory, falls
  back to `FX_MANUAL_RATE` from `.env` if unreachable.
- **The actual rate provider is an open decision, not yet picked** (planning.md Gaps)
  — settle it as part of this task, not a later surprise. Needs no auth/key for a
  basic USD/INR spot rate; pick whichever free option has the least friction.

## Out of scope

- No scheduler wiring (task 5) — these are standalone, independently callable/testable
  clients.
- No order placement/modification code, anywhere, ever — GET-only by construction
  (hard invariant from architecture.md, not just a scope note).

## Acceptance criteria

- Each client's `fetch_holdings()` can be called directly (e.g. from a Python REPL or a
  throwaway script) and returns a `list[NormalizedHolding]`.
- `paytmmoney.py`, called with real `.env` credentials, returns real holdings. **✅
  Verified 2026-07-19** — 23/23 real holdings parsed correctly against the live API,
  `close_price` populated on every one.
- `indmoney.py` returns the fixture data unchanged from `sample_data.py` while in mock
  mode.
- `fx.py` returns a plausible USD/INR rate, and falls back correctly when the rate API
  is unreachable (test by pointing at a bad URL temporarily).
- `grep` confirms zero POST/PUT/DELETE calls to any broker API anywhere in
  `integrations/`.
