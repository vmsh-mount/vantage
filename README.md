# Vantage

A local, single-user investment command center that consolidates PaytmMoney (India equity,
live API) and INDmoney (India + US equity) holdings into one view — net worth, allocation,
gain/loss, risk/concentration, tax opportunities, and per-holding trajectory — plus a
real AI panel ("Ask Vantage") that can answer questions about your actual portfolio, track
your investment thesis and conviction over time, log and grade concrete calls against real
market prices, and surface patterns in how you actually trade. A daily digest email keeps
you posted even when you're not looking at the app.

Everything here talks to your real brokers read-only — **no order-placement code exists
anywhere in this codebase**, for any broker, for any reason.

## Status

**Done.** Phase 1 (MVP dashboard) and Phase 2 (tax suggestions, deterministic fact tools,
the Vantage MCP server, the Ask Vantage panel, the daily digest, and the full persistent
agent-memory system — thesis tracking, decision grading, memory-poisoning defenses, an
agent-authored desk note, and a behavioral mirror) are all built, live-verified against real
broker data, and merged to `main`. See [docs/tasks/README.md](docs/tasks/README.md) for the
complete build history.

## Documentation map

This README is the entry point. Everything else lives in `docs/`:

| Doc | What's in it |
|---|---|
| [docs/features.md](docs/features.md) | **What you can do with the app** — every page, the Ask Vantage panel, the daily digest, page by page, in plain terms |
| [docs/architecture.md](docs/architecture.md) | **How it's built** — stack, project structure, data model, every backend subsystem, the full REST API surface, security model |
| [docs/mcp-tools.md](docs/mcp-tools.md) | **Full agent-tool reference** — every tool the AI panel can call, read vs. write, exactly what each does |
| [docs/planning.md](docs/planning.md) | **Why, Phase 1** — the original design rationale, query taxonomy, key decisions |
| [docs/planning-phase2.md](docs/planning-phase2.md) | **Why, Phase 2** — tax spine, MCP/agent architecture, the persistent-memory redesign (what the first attempt got wrong and why) |
| [docs/tasks/](docs/tasks/) | **Build history** — every task, in order, with real findings, bugs found and fixed, and live-verification traces. Start at [docs/tasks/README.md](docs/tasks/README.md) |
| [docs/ui-flow-prototype.html](docs/ui-flow-prototype.html) | Phase 1's clickable static mockup (historical reference, open directly in a browser) |

If you only read one other doc, make it **[docs/features.md](docs/features.md)** for what
it does, or **[docs/architecture.md](docs/architecture.md)** for how it's built.

## Prerequisites

- Python 3.11+
- Node.js 20+ (for the frontend)
- A PaytmMoney Open API key + secret — register a **Trading API** app at
  [developer.paytmmoney.com](https://developer.paytmmoney.com) (not *Publisher API*)
- An INDmoney (INDstocks) setup — client ID + TOTP setup key from
  [indstocks.com/app/api-trading](https://indstocks.com/app/api-trading); runs mocked
  until these are set
- The **`claude` CLI** (Claude Code) installed and logged in, for the Ask Vantage panel and
  daily digest agent section — bridge-server shells out to your own `claude` subscription
  auth, no separate API key needed. Everything else works fine without it.
- Optional: SMTP credentials (e.g. a Gmail app password) for the daily digest email

## Setup

**Backend:**

```bash
make setup   # create bridge-server/.venv, install dependencies
make env     # create bridge-server/.env from the template (won't touch an existing one)
```

Open `bridge-server/.env` and fill in `PAYTMMONEY_API_KEY`/`PAYTMMONEY_API_SECRET` (required
to start at all), and optionally `INDMONEY_CLIENT_ID`/`INDMONEY_TOTP_SETUP_KEY` and the
`SMTP_*`/`DIGEST_*` block. `.env` is gitignored — never commit it.

```bash
make login   # refresh both PaytmMoney (browser + OTP) and INDmoney (TOTP + MPIN) access tokens
make run     # start the dev server with reload, on http://127.0.0.1:8000
make health  # confirm it's up
```

**Frontend:**

```bash
cd deck-app
npm install
npm run dev   # http://localhost:5173
```

## Commands

| Command | What it does |
|---|---|
| `make setup` | Create `bridge-server/.venv` and install dependencies |
| `make env` | Copy `.env.example` → `bridge-server/.env` if one doesn't already exist |
| `make run` | Start the dev server (`uvicorn --reload`) on `http://127.0.0.1:8000` |
| `make login` | Refresh both PaytmMoney and INDmoney access tokens (one restart at the end) |
| `make login-paytmmoney` | Refresh just the PaytmMoney access token |
| `make login-indmoney` | Refresh just the INDmoney (INDstocks) access token |
| `make health` | `curl` the running server's `/api/health` |
| `make clean` | Remove `__pycache__` and the local SQLite file — **never touches `.env`** |
| `npm run dev` (in `deck-app/`) | Start the Vite dev server on `http://localhost:5173` |
| `npm run build` (in `deck-app/`) | Type-check + production build |

Override host/port with `make run HOST=0.0.0.0 PORT=9000`.

## Project structure

```
vantage/
  bridge-server/     # FastAPI backend — agent runner, MCP server, scheduler, digest,
                      # tax/statement parsing, broker integrations. See docs/architecture.md
  deck-app/           # React + TypeScript frontend — dashboard, manual holdings,
                       # thresholds, status, and the Ask Vantage side panel
  docs/                # everything described in the table above
  Makefile
```

Full layout, one line per file, in [docs/architecture.md](docs/architecture.md#project-structure).

## Security

- All secrets live in `bridge-server/.env` only — gitignored, never hardcoded, never
  committed. Your broker account MPINs are **never stored anywhere** — both login scripts
  prompt for them interactively and use them exactly once per run.
- Every broker client is GET-only by construction — this app cannot place, modify, or
  cancel an order for any broker, even if the API technically allows it.
- The AI panel runs in a locked-down sandbox: it can reach only Vantage's own tools (plus
  web search/fetch when explicitly enabled), never your filesystem, shell, or `.env`,
  regardless of working directory.
- Every broker API call is logged locally (`ApiCallLog` table + `logs/api_calls.log`) for
  your own audit trail.

Full detail, including the memory-poisoning defenses behind the agent's persistent memory,
in [docs/architecture.md#security](docs/architecture.md#security).

## License

[MIT](LICENSE)
