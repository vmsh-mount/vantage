# Vantage — Architecture

Companion to [planning.md](./planning.md) (Phase 1 design rationale) and
[planning-phase2.md](./planning-phase2.md) (Phase 2 design rationale) — those cover *why*,
this covers *how*, as the system actually is today. See [README.md](../README.md) for the
top-level map of every doc, [features.md](./features.md) for what you can actually do with
the app, and [mcp-tools.md](./mcp-tools.md) for the full agent tool reference.

## Stack

- **bridge-server**: Python 3.11+, FastAPI, SQLAlchemy + SQLite (WAL mode), APScheduler,
  httpx, the official `mcp` SDK (co-hosting Vantage's own MCP server), `pyotp` (local TOTP
  for INDmoney token refresh), `openpyxl`/`xlrd` (parsing PaytmMoney's `.xlsx`/`.xls`
  statement exports).
- **deck-app**: React 19 + TypeScript, Vite, `@tanstack/react-query`, `react-router-dom`,
  Recharts, `react-markdown` + `remark-gfm` (rendering the agent panel's responses). No
  separate state-management library — plain React Query cache + local component state.
- **Agent**: the real `claude` CLI (Claude Code), spawned as a subprocess per turn —
  `bridge-server` never calls a model API directly; it shells out to the same CLI you'd run
  interactively, scoped down to a locked allowlist (see [Security](#security)).
- **Storage**: one local SQLite file. No cloud dependency, no external database.

## Project structure

```
vantage/
  bridge-server/
    app/
      main.py                # FastAPI app, CORS, middleware, router registration,
                              # scheduler + MCP session-manager lifecycle
      config.py               # pydantic-settings: loads .env
      db.py                    # SQLAlchemy engine/session, WAL pragmas, self-healing
                                # column migrations (this project has no migration tool)
      scheduler.py              # APScheduler: sync pipeline (interval) + daily digest (cron)
      digest.py                  # daily deterministic email + best-effort agent section
      agent_runner.py             # one-shot `claude` subprocess wrapper (NDJSON streaming)
      agent_security.py            # the allowlist/scoping `claude` is spawned with
      run_context.py                # per-WS-connection provenance plumbing for memory-
                                     # poisoning defenses (ContextVars + ASGI middleware)
      vantage_mcp.py                 # Vantage's own MCP server — every agent tool lives here
      thesis.py, decisions.py,        # persistence for the agent-writable tables
        grading.py, behavioral.py      # + grading job + behavioral-pattern computations
      trajectory.py                    # per-holding Trajectory computation (task 7)
      regions.py                        # India/US region derivation helper
      integrations/
        base.py                          # NormalizedHolding schema + BrokerClient protocol
        paytmmoney.py                      # httpx client, live
        indmoney.py                         # httpx client, live once credentials exist
        indmoney_mcp.py                      # bridge-server as its OWN INDmoney MCP/OAuth
                                              # client (task 24) — separate from the agent's
                                              # own MCP connections
        fx.py, sample_data.py
      facts/
        volatility.py                     # volatility-scaled stop-loss suggestions (real
                                           # INDmoney OHLC)
        benchmark.py                       # per-holding return vs NIFTY 50 / FD-equivalent
      statements/
        tradebook.py, tax_pnl.py,           # parsers for PaytmMoney's three real Excel
          harvesting.py                      # statement exports (task 20/21)
      tax/
        suggestions.py                        # harvest-loss/gain + LTCG-crossing suggestions
      models/                                  # one file per table, __init__.py re-exports all
      schemas/                                  # one file per resource, mirrors models/
      routers/                                   # one file per resource — see API Surface
      audit_log.py                                # ApiCallLog writer + logs/api_calls.log
    scripts/
      login.py                    # unified PaytmMoney + INDmoney token refresh
      paytmmoney_login.py           # browser login flow → access token
      indmoney_login.py              # local TOTP + interactive MPIN → access token
      indmoney_mcp_login.py           # OAuth 2.1 + PKCE + DCR for bridge-server's own
                                       # INDmoney MCP client (task 24, persists to disk)
      _bridge_control.py               # shared restart/health-poll/env-write helpers
      *_smoke_test.py                   # real, non-mocked verification scripts for the
                                         # agent runner/security/WS/concurrency subsystems
    requirements.txt, .env.example
  deck-app/
    src/
      api/client.ts, types.ts    # typed REST client
      hooks/useAgentSocket.ts     # the /ws/agent WebSocket hook (task 28c/29)
      components/
        Layout.tsx                 # left nav + AiPanel mount (persists across page nav)
        AiPanel.tsx                  # the "Ask Vantage" side panel — reasoning blocks, tool
                                      # cards, markdown-rendered answers, UI-actions
      lib/format.ts, queries.ts, highlight.tsx
      pages/
        Dashboard.tsx, ManualHoldings.tsx, Thresholds.tsx, Status.tsx
  docs/
    planning.md, planning-phase2.md     # design rationale (Phase 1, Phase 2) — the "why"
    architecture.md                      # this file — the current "how"
    features.md                           # user-facing: what you can do with the app
    mcp-tools.md                           # full agent tool reference
    ui-flow-prototype.html                  # Phase 1 clickable static mockup (historical)
    tasks/                                   # every task, in build order, with real
                                              # findings/fixes/live-verification traces —
                                              # see tasks/README.md
  Makefile
  README.md
```

## Data model

One SQLite file (`bridge-server/vantage.db`, gitignored), WAL mode + `busy_timeout` so a
scheduled job and a live agent session can both write without "database is locked" (task
28d). This project has no migration tool — a column added after a table already shipped
gets a small, idempotent, self-healing `ALTER TABLE` in `db.py`'s `init_db()` instead (see
`_ensure_holdings_notes_column`, `_ensure_provenance_columns`).

**Portfolio state:**
- **`Holding`** — current state per broker+symbol, upserted every sync tick.
  `source='api'` (live-synced) vs `'manual'` distinguishes hand-entered US holdings from
  live ones — a broker's own live response is ground truth, so a symbol it stops reporting
  gets pruned, never left stale (task: stale-holdings-pruning fix).
- **`PortfolioSnapshot`** / **`HoldingSnapshot`** — one row per scheduler tick (portfolio-wide
  and per-holding), powering trend charts and the Trajectory feature — things a
  current-state-only table can't answer.
- **`RiskSettings`** — single-row table: concentration thresholds, target India:US split.
- **`Threshold`** — per-holding stop-loss/target, agent-writable via `set_threshold`.
- **`ApiCallLog`** — every broker API call, local audit trail.

**Trade history (PaytmMoney-only — task 20/21, explicit scope boundary):**
- **`Trade`** — raw trade-book rows, joined to `Holding` via ISIN (PaytmMoney's own
  `script_code` isn't a ticker).
- **`RealizedGain`** — PaytmMoney's own already lot-matched Tax P&L rows (FIFO done by the
  broker, not re-derived here).
- **`HarvestingPosition`** / **`HarvestingSummary`** — PaytmMoney's own Tax Gain/Loss
  Harvesting report, imported as-is.

**Digest:**
- **`DigestLog`** — one row per daily-digest run attempt; the durable half of the
  dead-man's-switch (task 27) — even if every send attempt fails, this row lets the *next*
  run notice the gap and lead with a warning.

**Agent memory (Phase 2 Half B — tasks 33–37):**
- **`Thesis`** — append-only, versioned investment-thesis entries per holding
  (`add_thesis_entry`/`get_thesis_history`). Coexists with, doesn't replace, `Holding.notes`
  (the cheap always-visible tier).
- **`DecisionLog`** — a concrete, checkable call captured at the moment it's made
  (`log_decision`), graded on-demand against real market prices
  (`POST /api/decisions/grade`) for **call quality** (was the prediction right), never user
  outcome.
- Both tables carry **`run_session_id`**, **`touched_untrusted_content`**,
  **`reviewed`** — memory-poisoning provenance/quarantine (task 35, see below).

Settings/secrets are **not** in the DB — `.env` only (see [Security](#security)).
`RiskSettings` is the one exception: user-adjustable app state, not a secret.

## Backend, layer by layer

**Integration layer** (`integrations/`) — `NormalizedHolding` is the one schema every
broker client returns; `BrokerClient` is a one-method protocol (`fetch_holdings()`). Broker
clients are **GET-only by construction** — no order-placement code exists anywhere in this
codebase, for any broker, for any purpose (see [Security](#security)). `indmoney_mcp.py` is
a second, separate INDmoney connection: bridge-server's *own* persistent OAuth client (used
by `facts/`), distinct from whatever MCP connection an interactive agent session has.

**Scheduler** (`scheduler.py`) — two jobs on one `BackgroundScheduler`:
1. `run_sync_pipeline` — interval (`REFRESH_INTERVAL_MINUTES`, default 20). Polls every
   active broker, normalizes, upserts `Holding`, prunes symbols a broker stopped reporting
   (guarded: never prunes on an empty/degraded API response), snapshots portfolio + every
   holding, logs every call.
2. `run_daily_digest` — cron, `Asia/Kolkata`, default 07:00. See **Digest** below.

**Statements + tax** (`statements/`, `tax/`) — PaytmMoney's three real Excel exports
(Trade Book, Tax P&L Statement, Tax Gain/Loss Harvesting Report) parsed and stored as-is;
`tax/suggestions.py` adds timing/framing on top (LTCG-crossing-soon, harvest-loss/gain
suggestions) — never re-derives FIFO lot-matching the broker's own export already did.

**Facts** (`facts/`) — the only two features that call INDmoney's *market-data* MCP tools
(`get_indian_stocks_ohlc`, `lookup_ind_keys`) rather than the portfolio-holdings endpoints:
volatility-scaled stop-loss suggestions and per-holding return vs. NIFTY 50 / an
FD-equivalent rate, both real-OHLC-only, never fabricated, both explicit about the real
1-year OHLC lookback ceiling INDmoney's API has.

**Vantage's own MCP server** (`vantage_mcp.py`) — co-hosted inside bridge-server via
streamable-HTTP (mounted at `/mcp`), not a separate stdio child process — that's what lets
every tool call directly into this same process's already-verified functions with no extra
HTTP round-trip. Every tool is described in full in [mcp-tools.md](./mcp-tools.md).

**Agent runner + security + WS bridge** (`agent_runner.py`, `agent_security.py`,
`routers/agent_ws.py`) — `run_one_shot` launches a real `claude -p --output-format
stream-json` subprocess and yields parsed NDJSON events as they arrive.
`build_scoped_extra_args` is the *only* place that decides what a spawned agent can reach:
`--strict-mcp-config` naming only Vantage's own MCP server, `--tools`/`--allowedTools`/
`--disallowedTools` fail-closed (`--permission-mode dontAsk`), `.env`/`Bash`/`Read`/`Write`
never reachable regardless of working directory. `/ws/agent` is the multi-turn bridge the
panel talks to: one `run_one_shot` call per browser message, `--resume` once a session
exists, conversation history lives in the `claude` CLI's own session file (not in
bridge-server memory).

**Memory-poisoning defenses** (`run_context.py`) — the provenance layer behind `Thesis`/
`DecisionLog`'s quarantine columns. A bridge-server-generated per-connection `run_key` is
baked into the agent's own MCP config URL query string; a plain ASGI middleware (not
Starlette's `BaseHTTPMiddleware` — that silently drops `ContextVar`s across its internal
task boundary, a real bug found and fixed live, see
[35-memory-poisoning-defenses.md](./tasks/35-memory-poisoning-defenses.md)) reads it back
out per-request and exposes it to write tools via `ContextVar`s. A post-turn reconciliation
pass closes a second real race (a web-tool call and a write-tool call dispatched in
parallel within one turn). Quarantine only ever lifts via explicit human review
(`POST /api/quarantine/{table}/{id}/review`) — never automatically.

**Digest** (`digest.py`) — composed and sent **entirely in Python**, no agent dependency,
so it genuinely always sends regardless of INDmoney/Claude Code availability. A
dead-man's-switch (`DigestLog`) leads the next email with a warning if the previous run
failed or didn't happen at all. On top of that guaranteed path, a second, **best-effort**
"Agent's take" section (task 36) runs one real `run_one_shot` turn (read-only,
`enable_web=True` so it can cite news) under a hard 150-second budget — any failure or
timeout is caught internally and silently omits the section; it can never block the
guaranteed send.

**Grading** (`grading.py`) — `POST /api/decisions/grade`, on-demand only (never
scheduler-driven, to avoid contending with INDmoney's real ~30-calls/min rate limit).
Fetches real OHLC at each decision's horizon date and evaluates its `success_criterion`;
`inconclusive` (never a guessed `met`/`not_met`) when the OHLC history doesn't reach that
far back.

**Behavioral mirror** (`behavioral.py`) — three patterns computed directly from `Trade`/
`RealizedGain`: disposition effect (hold winners shorter than losers?), averaging-down
frequency (bought more while already below your running cost basis?), win/loss asymmetry
(win rate, gain/loss ratio). PaytmMoney-only, same boundary as the tax/benchmark features.

## REST API surface

| Area | Endpoints |
|---|---|
| Dashboard | `GET /api/dashboard`, `GET /api/trend`, `GET /api/alerts`, `GET /api/risk` |
| Manual holdings | `POST/PUT/DELETE /api/holdings/manual`, `PUT /api/holdings/{id}/notes`, `POST /api/holdings/manual/import-csv` |
| Thresholds & risk settings | `GET/POST/PUT/DELETE /api/thresholds`, `GET/PUT /api/settings/risk` |
| Status & sync | `GET /api/status`, `POST /api/refresh` |
| Statements import | `POST /api/statements/tradebook`, `POST /api/statements/tax-pnl`, `POST /api/statements/harvesting` |
| Tax | `GET /api/tax/suggestions` |
| Facts (real OHLC) | `GET /api/facts/volatility-stops`, `GET /api/facts/benchmark` |
| Decisions | `POST /api/decisions/grade` (the only REST surface — reading/writing individual decisions is agent-only, see mcp-tools.md) |
| Quarantine | `GET /api/quarantine`, `POST /api/quarantine/{table}/{id}/review` |
| Agent | `WS /ws/agent` (multi-turn panel bridge) |
| Health | `GET /api/health` |

Full request/response schemas live in `bridge-server/app/schemas/` — one file per
resource, named to match its router.

## MCP tool surface

16 tools, all served from Vantage's own MCP server (`vantage_mcp.py`) and reachable only by
an agent spawned through `agent_security.build_scoped_extra_args` — never exposed to the
outside world directly. Full table (name, read/write, what it does, which task added it) in
[mcp-tools.md](./mcp-tools.md). One write tool, `set_threshold`, and the panel-only ones
(`add_thesis_entry`, `log_decision`, `set_decision_status`, `highlight_holding`) are the
only tools that ever change state — every other tool is read-only.

## Frontend

Single-page app (`react-router-dom`), left nav + main content per page, plus the **Ask
Vantage** panel (`AiPanel.tsx`) mounted once in `Layout.tsx` (sibling to the routed
content) so its WebSocket connection and conversation persist across page navigation. Four
routed pages — Dashboard, Manual Holdings, Thresholds, Status — each backed by
`@tanstack/react-query` against the typed `api/client.ts`. The panel renders reasoning
blocks, tool-call cards (correlated `tool_use`/`tool_result` pairs — a real bug this task's
own testing caught: never claim an action succeeded before its result confirms it), and the
final answer as real rendered markdown (`react-markdown` + `remark-gfm`).

## Security

- **Credentials**: all secrets in `bridge-server/.env` only — gitignored, never
  hardcoded, never committed, `chmod 600` recommended. Your PaytmMoney account MPIN and
  INDmoney account MPIN are **never stored anywhere** (DB, `.env`, logs) — both login
  scripts prompt for them interactively and use them exactly once per run.
- **Read-only to every broker, forever**: no order-placement/modification/cancellation
  code exists anywhere in this codebase, for any broker. This is enforced by what's
  implemented, not by requesting a read-only API scope.
- **Agent sandboxing**: a spawned `claude` process can reach *only* Vantage's own MCP
  server and (when explicitly enabled per call site) `WebFetch`/`WebSearch` — confirmed
  live that a bare `claude -p` otherwise inherits your entire ambient MCP config, and that
  `.env` is reachable by absolute path regardless of working directory unless the `Read`
  tool itself is excluded (the actual boundary, not cwd scoping). Fail-closed permission
  mode (`--permission-mode dontAsk`) denies anything off the allowlist outright.
- **Exfiltration guard**: when web access is enabled, an explicit system-prompt addendum
  tells the agent fetched content is untrusted data, never instructions, and it must never
  construct a URL embedding portfolio data — tested live against real adversarial pages.
- **Memory-poisoning defenses**: see the dedicated section above — provenance tagging +
  human-only quarantine on every agent-writable table.
- **Local audit trail**: `ApiCallLog` table + `logs/api_calls.log` for every broker call;
  `logs/digest_failures.log` for digest composition/send failures.

## Where to look next

- **[README.md](../README.md)** — setup, running the app, the full doc map.
- **[features.md](./features.md)** — what you can actually do with the app, page by page.
- **[mcp-tools.md](./mcp-tools.md)** — every agent tool, in detail.
- **[planning.md](./planning.md)** / **[planning-phase2.md](./planning-phase2.md)** — why
  the system is shaped this way, including cut features and deferred/later-revived designs.
- **[tasks/](./tasks/)** — the full build history, one file per task, each with real
  findings, bugs found and fixed, and live-verification traces — the most detailed record
  of *why* any specific line of code looks the way it does.
