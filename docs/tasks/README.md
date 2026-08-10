# Vantage — Task Breakdown (build history)

Companion to [../planning.md](../planning.md), [../planning-phase2.md](../planning-phase2.md)
(the *why*), and [../architecture.md](../architecture.md) (the current *how*). This folder is
the full build history: every task, in build order, each stating its scope, explicit
non-goals, and — for anything with real-world behavior to check — a live-verification trace
(real broker data, real subprocess runs, real emails sent, real bugs found and fixed). Kept
here permanently, not just during review, as the most detailed record of *why* any specific
line of code looks the way it does.

**Everything below is done and merged to `main`.**

## Phase 1 — MVP (bridge + deck)

| # | Task | Depends on |
|---|---|---|
| 1 | [Project scaffold & config](01-project-scaffold.md) | — |
| 2 | [Data models](02-data-models.md) | 1 |
| 3 | [Broker integration layer](03-broker-integrations.md) | 1, 2 |
| 4 | [PaytmMoney auth CLI](04-paytmmoney-auth-cli.md) | 3 |
| 5 | [Scheduler & sync pipeline](05-scheduler-sync-pipeline.md) | 2, 3 |
| 6 | [Dashboard API](06-dashboard-api.md) | 5 |
| 7 | [Trajectory](07-trajectory.md) | 5, 6 |
| 8 | [Risk & Alerts API](08-risk-alerts-api.md) | 5, 6, 7 |
| 9 | [Trend API](09-trend-api.md) | 5 |
| 10 | [Manual holdings & CSV import](10-manual-holdings-csv.md) | 2 |
| 11 | [Thresholds & Risk Settings CRUD](11-thresholds-risk-settings.md) | 2 |
| 12 | [Status, audit log & manual refresh](12-status-audit-refresh.md) | 5 |
| 13 | [Frontend scaffold & API client](13-frontend-scaffold.md) | — |
| 14 | [Dashboard: hero, trend, alerts, risk](14-dashboard-tier1.md) | 13 |
| 15 | [Dashboard: breakdowns & holdings table](15-dashboard-tier2.md) | 14 |
| 16 | [Manual Holdings page](16-manual-holdings-page.md) | 13 |
| 17 | [Thresholds & Risk Settings page](17-thresholds-page.md) | 13 |
| 18 | [Status page & manual refresh](18-status-page.md) | 13 |
| 19 | [Cross-page integration & E2E walkthrough](19-integration-e2e.md) | 14–18 |

## Phase 2, Half A — tax spine, facts, MCP, agent panel, digest

| # | Task | Depends on | Notes |
|---|---|---|---|
| 20 | Tradebook schema spike | — | A quick investigative task, resolved directly in [planning-phase2.md](../planning-phase2.md) (task table row 20) rather than its own doc — real PaytmMoney exports pulled and inspected: all three are genuine Excel, joined on ISIN |
| 21 | [PaytmMoney statement import](21-paytmmoney-statement-import.md) | 20 | Trade Book, Tax P&L, Harvesting Report parsers |
| 22 | [Tax suggestions](22-tax-suggestions.md) | 21 | Harvest-loss/gain, LTCG-crossing-soon |
| 23 | [Token-refresh helper + MCP longevity log](23-token-refresh-mcp-longevity.md) | — | See also the live [OAuth longevity log](23-mcp-oauth-longevity-log.md) |
| 24 | [bridge-server as INDmoney MCP/OAuth client](24-indmoney-mcp-client.md) | 23 | |
| 25 | [Deterministic fact tools](25-deterministic-fact-tools.md) | 24 | Volatility stops, NIFTY/FD benchmark |
| 26 | [Vantage MCP server](26-vantage-mcp-server.md) | 25 | Read tools + `set_threshold` write tool |
| 27 | [Daily deterministic email digest](27-daily-digest-email.md) | 22, 25 | No agent dependency, always sends |
| 28a | [One-shot Claude Code runner core](28a-one-shot-runner-core.md) | 26 | |
| 28b | [Security allowlist + fail-closed permission mode](28b-security-allowlist.md) | 28a | |
| 28c | [Multi-turn + WebSocket bridge](28c-multiturn-websocket.md) | 28b | |
| 28d | [Concurrency & SQLite WAL](28d-concurrency-wal.md) | 28c | |
| 28e | [Web search/fetch + exfiltration guard](28e-web-search-fetch.md) | 28b | |
| 32 | [Holding notes](32-holding-notes.md) | — | The cheap, always-visible tier of Half B's thesis idea |
| 29 | [Ask-your-portfolio panel](29-ask-your-portfolio-panel.md) | 28, 32 | The "Ask Vantage" side panel. Its "Out of scope" note also documents a same-day reversal (real markdown rendering, added after initial ship) |
| — | [Fix: stale holdings never pruned](fix-stale-holdings-pruning.md) | — | User-reported bug, root-caused and fixed generally |
| — | [INDmoney TOTP login automation](indmoney-totp-login.md) | — | Local TOTP computation, account MPIN never stored |

Task numbering here is lettered (`28a`–`28e`), not renumbered, so later "depends on 28"
references stay valid without meaning "all five parts." See
[planning-phase2.md §6.1](../planning-phase2.md) for the full breakdown rationale.

## Phase 2, Half B — persistent agent memory

| # | Task | Depends on | Notes |
|---|---|---|---|
| 33 | [Thesis + conviction](33-thesis-conviction.md) | 29 | Append-only, versioned, coexists with task 32's holding notes |
| 34 | [Decision log with real grading](34-decision-log-grading.md) | 33 | Grades call quality, not user outcome — on-demand only |
| 35 | [Memory-poisoning defenses](35-memory-poisoning-defenses.md) | 33, 34 | Provenance + sticky, human-only quarantine. Two real bugs found and fixed live |
| 36 | [Agent-authored desk note](36-agent-authored-desk-note.md) | 33, 35, 27, 28a | Augments, never replaces, the guaranteed digest send |
| 37 | [Behavioral mirror](37-behavioral-mirror.md) | 21 | Fully independent — only needs the Trade Book import |

See [planning-phase2.md §7.1](../planning-phase2.md) for the full breakdown rationale.

## How to read these

Each task file states its scope, explicit non-goals, the exact API/data fields it depends
on, and how completion was actually checked — for anything with observable real-world
behavior, that means a live-verification trace (real broker responses, a real subprocess
run, a real email received, a hand-recomputed number), not just "the code ran without
error." Several files also document a real bug found during that verification and how it
was fixed — read those sections if you're about to touch the same code path, they're the
fastest way to avoid re-discovering the same bug.
