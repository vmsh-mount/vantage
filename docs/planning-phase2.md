# Vantage — Phase 2 Planning: The Opinionated Research Engine

Companion to [planning.md](planning.md) and [architecture.md](architecture.md). Phase 1
(the read-only dashboard: bridge-server + deck-app, tasks 1–19) is built, live against both
brokers, and merged.

**This is the v2 plan, rewritten 2026-07-23** after a multi-angle review of v1 — feasibility,
product scope, design integrity, and external-dependency risk. The v1 plan tried to ship a
persistent-memory + unattended-automation layer alongside the deterministic core. The review
showed that layer was simultaneously the most expensive, the most likely to rot, and **broken
as specified** — and that the v1 security story had a real hole. This rewrite acts on all of
that; the reasoning behind each correction is recorded inline in the sections below rather
than in a separate review doc.

**What changed at a glance:**
- **Split into Half A (build now) and Half B (deferred, with its known defects documented).**
- **The security model is corrected** — the v1 "three enforcement layers" claim was false; §2
  now states the two invariants that actually matter.
- **The daily email is Python-owned**, not agent-composed, so it genuinely always sends.
- **Deterministic-fact tools get a real market-data path** (bridge-server becomes its own
  INDmoney client) instead of an impossible one.
- **IPO radar / GMP cut.** US OHLC-derived features declared India-only. Graph errors fixed.

**Update 2026-07-23, post-task-20:** the tradebook schema spike (§6, task 20) landed and it
substantially shrinks task 22. PaytmMoney's own exports already do FIFO lot-matching and
loss-harvesting math — the tax engine is now "parse broker output + add timing logic," not
"implement Indian capital-gains law." Details in §5.1 and §6. **Scope for now: PaytmMoney
only** — INDmoney tradebook/tax data isn't being pursued this phase (explicit user decision);
INDmoney MCP features (whole-net-worth, live prices, OHLC) are unaffected since they don't
depend on tradebook data.

**Update 2026-08-08, post-task-27:** tasks 20–27 are all done and merged. Task 28 ("Claude Code
runner") is broken into five sequenced sub-tasks, **28a–28e**, rather than one multi-week branch —
same task-numbering convention as everywhere else in this doc, lettered rather than renumbered so
tasks 29's and 31's existing "depends on 28" references stay valid without having to mean "all
five parts finished." Full breakdown in §6.1.

**Update 2026-08-10, post-task-37:** all of Half B (§7) is done — tasks 33–37, done and merged, full
breakdown in §7.1. Every §7 "must be fixed first" defect (unbuildable grading, non-versioned thesis,
untimestamped conviction, memory-poisoning) was actually fixed, not carried forward unresolved; two
genuine bugs were found and fixed via live testing along the way (task 35's doc has the full trace).
Phase 2 as scoped in this document is now fully shipped.

---

## 1. The reframe (unchanged in spirit, narrowed in scope)

A dashboard is passive: it shows numbers, you interpret them. Phase 2 makes Vantage behave
like an opinionated analyst — **but it earns that role through on-demand reasoning over
verifiable facts, not through a journaling ritual and a self-graded scorecard.**

What survives from v1: opinionated with clear reasoning; every opinion sits on a number you
can verify; Claude Code embedded as a side panel on your subscription (no API metering).

What's deferred: persistent memory, thesis journaling, conviction scoring, and the graded
track record (§7). The v1 claim that *"trust is earned from a visible track record"* rested on
a grading mechanism that no task actually built. Rather than assert it, Half A earns trust the
cheaper way — by showing its work, every time, with sources.

## 2. Invariants (corrected)

1. **Read-only to the broker and the market, forever.** Vantage never places, modifies, or
   cancels an order; never moves money. Stop-loss, buy, sell — you perform manually in the
   broker app. Vantage's job ends at "here's what I'd do and why."

2. **The two enforcement rules that actually matter.** v1 claimed three layers; the third
   ("the allowlist contains no order tool") was **security theatre** — no MCP server exposes
   an order tool, so it protected against nothing. The real threat is a *generic* tool plus
   credentials on disk. `bridge-server/.env` holds `PAYTMMONEY_API_KEY`,
   `PAYTMMONEY_API_SECRET`, `PAYTMMONEY_ACCESS_TOKEN`, and `INDMONEY_ACCESS_TOKEN` (verified)
   — an agent able to read that file and make an outbound request could authenticate to
   PaytmMoney directly and bypass "no order code exists" entirely. Therefore:
   - **(a) `Bash`, `Read`, `Write`, `Edit`, `NotebookEdit`, and `Task` stay off the agent's
     allowlist entirely** — enforced via `--tools ""` (disables every built-in tool) plus
     `--disallowedTools` naming them explicitly as defense-in-depth, not just "not on the
     allowlist by omission."
   - **(b) Corrected 2026-08-08 (task 28b) — the original wording here ("a working directory
     that does not contain it") was tested directly and is *wrong*: a `claude` subprocess with
     `Read` allowed can open a file by **absolute path** regardless of its working directory —
     confirmed live, it read `bridge-server/.env` from an unrelated cwd and printed the real
     API keys/tokens/SMTP password. Working-directory scoping is not a real boundary for file
     tools. **The only mechanism that actually holds is (a): `.env` is safe because `Read` is
     never reachable at all**, not because of where the process happens to be launched from.
     `chmod 600` remains good hygiene; it was never the load-bearing control either.
   - **(c)** The agent's MCP surface is scoped to **only Vantage's own MCP server** (task 26) via
     `--strict-mcp-config` + an explicit `--mcp-config` — confirmed live that a bare `claude -p`
     otherwise inherits the *user's entire ambient MCP config* (personal notes, Google Drive
     **including its write tools**), none of which has anything to do with Vantage.

   Supporting controls: the unattended run sets an explicit **`--permission-mode dontAsk`**
   (confirmed live: denies anything off `--allowedTools` with a clear message, never hangs
   waiting for a prompt that can't be answered, never falls back to broader access) so it fails
   closed instead of blocking on a prompt at 6 AM; the **email recipient is hardcoded in Python**, outside any
   agent-visible argument, so injection can't redirect it.

3. **Untrusted web content is a live threat, not a footnote.** The agent has portfolio data in
   context and outbound fetch. Injected content can attempt **exfiltration** (`…/?d=<holdings>`),
   not just bad advice. "Worst case is a suggestion you reject" was wrong — it reasoned only
   about the broker boundary. Mitigations: web fetch is read-only and results are always
   attributed; no tool may take a URL assembled from portfolio data; a deterministic
   price/fundamental condition must co-fire before any "thesis broken" style verdict, so
   unverifiable narrative never drives a headline call on its own.

4. **Local, single-user.** No multi-tenant, no cloud, no accounts.

5. **Facts are computed, opinions are reasoned — with provenance.** v1 asserted this but made
   it unenforceable: an LLM can emit a computed-*looking* number without calling anything.
   So every number rendered in the panel or the email **carries a reference to the tool result
   that produced it**; un-sourced numbers render as opinion, not fact.
   *Reconciling the v1 self-contradiction:* XIRR is **vendor-supplied** for INDmoney assets
   (`networth_holdings`) and **self-computed** for PaytmMoney assets. Both are labelled with
   their source rather than presented as one uniform "fact."

## 3. External data surface (what's actually available)

**INDmoney MCP** — `https://mcp.indmoney.com/mcp`, streamable-http, OAuth 2.1 + PKCE,
short-lived auto-rotating read-only tokens. Live tools confirmed in-session:
`networth_snapshot`, `networth_holdings`, `networth_allocation_breakdown`,
`get_indian_stocks_ohlc`, `get_indian_stocks_details`, `get_indian_stocks_movers`,
`get_us_stocks_details`, `get_mf_by_category`, `get_mf_funds_details`, `indian_stocks_sips`,
`mf_sips`, `user_watchlist`, `lookup_ind_keys`, plus option-chain/Greeks.

Honest constraints on it:
- **India-only history.** `get_indian_stocks_ohlc` has no US counterpart —
  `get_us_stocks_details` gives live *price*, not history. **All OHLC-derived features
  (vol-scaled stops, benchmark/opportunity-cost, Trajectory) are India-only.** This is Phase
  1's US gap (P1 Decisions #1, #9) still unsolved, not resolved.
- **Single-vendor beta, load-bearing.** A point-in-time tool list is not a contract. Mitigation:
  a **contract smoke-test** (task 24) asserting expected tools and response shapes still exist,
  so drift is caught loudly instead of silently corrupting output. The Phase-1 INDstocks REST
  path is the **degraded backup**, not a cleanly separate consumer.
- **"Read-only by construction" is a bonus, not a security layer.** The vendor could add write
  tools to the same endpoint; the allowlist is the actual guard.
- **Analyst consensus/news is not in the connected tool set.** Sourced via agent web search
  instead (§5), with the honest gap that structured Indian target prices are hard to get free.

**Token reality.** The INDstocks REST token dies daily at 6 AM by design; its only automation
is auto-login, which needs OTP/credential handling we will **not** do. The MCP OAuth token
auto-rotates and *may* need re-consent only occasionally — **unmeasured**. Task 23 measures it
before anything depends on the answer.

## 4. Architecture

**Vantage MCP — co-hosted in FastAPI over HTTP/SSE.** Not a stdio child of `claude`. This
transport choice is what makes UI-actions possible at all: a stdio subprocess has no path back
to the browser, whereas an HTTP/SSE server inside FastAPI can bridge an agent tool call onto
the existing WebSocket to the React SPA. (Tolaria gets this comparatively free as one Tauri
process with native webview IPC; ours is browser ↔ FastAPI ↔ subprocess ↔ MCP — more moving
parts than "same shape, our stack" implied.)

**How market data reaches the deterministic fact layer.** An MCP *server* cannot be a client of
another MCP server, so the v1 design — Python "fact" tools computing from OHLC "pulled via the
INDmoney MCP" — was impossible. Resolution: **bridge-server becomes its own INDmoney OAuth/MCP
client** (task 24), so Python fetches OHLC itself and the deterministic framing holds. The
alternative (agent passes OHLC into the tool) was rejected: it reintroduces exactly the
eyeball/injection risk invariant #5 exists to prevent.

**Two runner modes, not one.** v1's "both run the same generator" conflated two different
things:
- **One-shot** (`claude -p --output-format stream-json`) — for scheduled/batch work.
- **Multi-turn** (`--resume`/`--session-id`, or bidirectional `--input-format stream-json`) —
  for the interactive panel.

The runner also owns, non-trivially: `asyncio.create_subprocess_exec` + WS streaming (new
territory — Phase-1 routers are sync `def` on a threadpool with a threaded APScheduler), NDJSON
framing and partial-JSON handling, mid-tool-call crash handling, backpressure to a slow
browser, and **concurrency** (a scheduled job and a live panel session can both spawn `claude`
and write the same SQLite → **WAL mode + serialized writes**).

**Pin the `claude` CLI version** you validate against and smoke-test the NDJSON parser; that
interface evolves.

## 5. Half A — build now

Rot-proof, high-value, no maintenance ritual demanded of you.

1. **Tax engine.** The highest-value feature in the plan: converts directly into rupees saved,
   needs zero upkeep, can't rot, genuinely India-specific, and no broker app does it. LTCG/STCG
   at the 1-year line, the ₹1.25L exemption, and loss-harvesting suggestions.
   **Rescoped after task 20 (§6):** the FIFO lot-matching, grandfathering, and split/bonus
   handling this pillar originally budgeted as hard, from-scratch engineering **turns out to
   already be done by PaytmMoney itself.** Their real exports, pulled and inspected in task 20:
   - **Tax P&L Statement** (`.xlsx`) — realized gains, already lot-matched: every sold position
     broken into individual lots with buy date/price, sell date/price, and net P&L, correctly
     bucketed into Short-Term vs Long-Term sections. Includes lots bought back in 2021–2022, so
     the aging/classification logic is already handled.
   - **Tax Gain/Loss Harvesting Report** (`.xls`) — goes further: realized STCG/LTCG for the FY,
     **unrealized** P&L per currently-held position, the exact rupee amount of harvestable
     loss/gain, and even a ready-made "book this small gain under the ₹1.25L exemption" bucket.
   - **Trade Book** (`.xlsx`) — the one thing the other two don't give: buy dates for positions
     you *still hold* (needed for §5.6's LTCG-crossing-soon suggestions, since the harvesting
     report has buy *average* but not buy *date*).

   So this pillar is now: **parse these three PaytmMoney exports into our schema, then layer
   Vantage-specific timing and framing on top** ("book RAMASTEEL's loss before March 31 — offsets
   ₹X of your realized gains") — not building tax-lot logic from raw trades. Materially smaller
   than P1 Key Decision #6 anticipated when it deferred this. **PaytmMoney-only for now** (see
   the 2026-07-23 update above); still a hard dependency on the import (task 21), just a
   lighter one downstream (task 22).
2. **Whole-net-worth view.** Best value-per-effort in the document: render `networth_snapshot`
   / `networth_allocation_breakdown` from an MCP we're already connecting. Fixes Phase 1's
   equity-only gap (MF, US, FD, EPF, NPS, …). Zero upkeep.
3. **Ask-your-portfolio panel.** The agent workhorse: on-demand reasoning over the
   deterministic fact-tools plus **cited web search** for news/analyst commentary. This is
   where the "opinionated analyst" reframe earns its keep cheaply — no journaling ritual, no
   memory tables, no grading apparatus.
4. **Daily deterministic email digest.** You asked for daily; this delivers it *without* the
   agent-dependency that made v1's version fragile. **Python composes and sends** from whatever
   is in the DB: holdings, tax/LTCG dates approaching, threshold breaches, concentration flags.
   No agent, no MCP mesh, no auth fragility — so it genuinely always sends. A **dead-man's
   switch** reports its own failure loudly. Agent-authored ranked reasoning layers on later
   (§7) once we know from use what belongs in it.
   *Setup friction to expect:* SMTP credentials in `.env`, and residential-IP mail can land in
   spam without SPF/DKIM — tolerable when mailing yourself.
5. **Smart stop-loss / target suggestions (India-only).** Volatility-scaled: stop ≈ 2–3× the
   holding's own daily volatility (bounded), computed in Python from OHLC that bridge-server
   fetches itself (§4), shipped with its reasoning ("ZAGGLE swings ~2.4%/day; a −7% stop ≈
   three bad days"). Feeds the Phase-1 thresholds you already have.
6. **Opportunity-cost / benchmark (India-only).** Per holding over its *actual* holding period —
   buy date comes from the **Trade Book** import specifically (the Tax P&L / Harvesting exports
   don't carry buy dates for still-held positions, only realized lots and buy-averages,
   per task 20's findings): your return vs an FD rate and vs NIFTY 50.

**Presentation principle — clarity over volume.** Goal is *"clear visibility to make the
decision,"* not loudness. Ranked, reasoned list; most-important-first; each item states action
+ why-with-a-number + the decision it implies. A small **"needs attention now"** section pinned
at top for genuinely time-sensitive items (LTCG date crossing, stop breached) — surfaced, never
a modal nag. Tune loudness after living with it.

## 6. Half A task breakdown

Continues Phase-1 numbering. Detailed task files (Depends-on / Unlocks / Goal / Scope /
Out-of-scope / Acceptance-criteria, same format as `docs/tasks/01–19`) to be written after this
plan is reviewed.

| # | Task | Depends on | Notes |
|---|---|---|---|
| 20 | ~~Tradebook schema spike~~ — **done 2026-07-23** | — | **Resolved.** PaytmMoney-only, per user decision. Real exports pulled and inspected: all three are genuine Excel (`.xlsx`/legacy `.xls`), no PDF. **Trade Book** = raw trades (`Date, Script, ISIN, Exchange, Product Type, Type, Quantity, Price, Brokerage, ETT, GST, STT, SEBI, Stamp Duty, Order Number, Trade Number, Trade Time`; note `Script` is PaytmMoney's internal numeric code, not a ticker — join on **ISIN**). **Tax P&L Statement** = already lot-matched realized gains, ST/LT split, per-lot buy/sell date+price. **Tax Gain/Loss Harvesting Report** = unrealized P&L per current holding + exact harvestable amounts. See §5.1 for what this changes |
| 21 | PaytmMoney statement importer — ingest all **three** export types into normalized tables | 20 | **Two different update semantics, not one:** Trade Book is an immutable event log → incremental/append, idempotent dedupe by Order+Trade Number (date-range re-uploads must not duplicate). Tax P&L and Harvesting Report are broker-recomputed snapshots for a period/as-on-date → **replace-on-import** (a fresher upload supersedes the prior one for that FY), not appended. Occasional, user-initiated, not daily |
| 22 | Tax suggestions — parse the **already-lot-matched** Tax P&L + Harvesting Report data, add Vantage's own timing/framing (FY-end proximity, LTCG-crossing-soon using Trade Book buy dates) | 21 | **Shrunk by task 20's finding** — no FIFO/grandfathering/split logic to build ourselves; PaytmMoney's compliance-grade lot matching is the input, not something we reconstruct. Budget for the parsing + presentation layer, not tax law |
| 23 | Token-refresh helper + **MCP OAuth longevity measurement** | — | One-tap login helper (extends `paytmmoney_login.py`); **measures** re-consent frequency. Gates anything that assumes live data |
| 24 | bridge-server as INDmoney MCP/OAuth client + **contract smoke-test** | 23 | The market-data path for the fact layer (§4); smoke-test guards vendor drift |
| 25 | Deterministic fact tools — tax, concentration, vol-scaled stops, benchmark — with **provenance-tagged results** | 22, 24 | Vol-stops/benchmark are **India-only** |
| 26 | Vantage MCP server — co-hosted in FastAPI over **HTTP/SSE**, read tools + UI-action tools | 25 | Transport choice is what enables UI-actions (§4) |
| 27 | Daily deterministic email digest — **Python-composed and sent**, dead-man's switch | 22, 25 | No agent dependency; always sends |
| 28 | Claude Code runner — **multi-turn** for the panel, scoped allowlist per §2, web search/fetch | 26 | **Broken into 28a–28e, see §6.1** — multi-week subsystem; async subprocess, NDJSON, WAL, concurrency |
| 29 | Ask-your-portfolio panel (deck-app) — AiPanel: reasoning blocks, tool cards, composer, UI-actions, clarity-first layout | 28, 32 | **Reads the holding notes from 32**, so the agent can reason about *why* you own something |
| 30 | Whole-net-worth view on the dashboard | 24 | The first genuinely visible win once the 23 → 24 chain lands |
| 31 | Unattended-run reliability + quota-headroom validation | 28 | Before any scheduled *agent* run exists (§7) |
| 32 | **Holding notes** — nullable free-text "why I own this" per holding + an input on the holdings row | — | Tiny (one column + one input). Independent of everything; do it whenever. The kept-cheap piece of Half B (§7) |

Sequence: **20 is done** — **21 → 22** (the tax spine, both lighter than originally scoped) with
**23 → 24** in parallel; then **25 → 26** (fact layer + MCP); **27** (daily email) is the first
*agent-free* deliverable, though it still waits on 22 and 25; then **28 → 29** (the agent panel).
**30** needs the 23 → 24 chain behind it. **32** depends on nothing and can be slotted in at any
point — worth doing early so notes start accumulating before 29 exists to read them.

**20–27 done 2026-08-08.**

## 6.1 Task 28 breakdown (added 2026-08-08)

Task 28 is decomposed into five sequenced sub-tasks — lettered, not renumbered, so tasks 29's and
31's existing "depends on 28" references still mean what they say without needing to enumerate
all five. Each is independently buildable, branch-able, and verifiable against real behavior —
same standard as every task so far, not config that merely "looks right."

| # | Task | Depends on | Notes |
|---|---|---|---|
| 28a | One-shot runner core — `asyncio.create_subprocess_exec` around `claude -p --output-format stream-json`, NDJSON framing + partial-JSON handling | 26 | Foundational; no WS, no tools yet. Pin the `claude` CLI version validated against + a smoke-test guarding drift (§4) |
| 28b | Security: scoped allowlist + fail-closed permission mode | 28a | The actual enforcement of invariant #2 — explicit `--permission-mode` that auto-denies non-allowed tools, `.env` structurally unreachable from the agent's working directory. Verified by attempting a denied tool call and confirming refusal, not just reading config back |
| 28c | Multi-turn + WebSocket bridge | 28b | `--resume`/`--session-id` (or bidirectional `--input-format stream-json`), new FastAPI WS endpoint, live streaming to the browser, backpressure handling. The genuinely new territory — everything through task 27 is sync `def` on a threadpool with a threaded APScheduler |
| 28d | Concurrency & SQLite WAL | 28c | WAL mode + serialized writes so a scheduled job (task 27's digest, task 5's sync tick) and a live panel session can both spawn `claude` and touch the same SQLite file without "database is locked." Mid-tool-call crash handling for a `claude` process dying mid-call |
| 28e | Read-only web search/fetch + exfiltration guard | 28b | Adds web search/fetch to the allowlist, read-only, results always attributed, no tool may build a URL from portfolio data (invariant #3). Verified with an actual adversarial test page, not just a code read |

Sequence: **28a → 28b**, then **28c and 28e can run in parallel** (both only need 28b's allowlist
mechanism, not each other), then **28d** (only a real risk once 28c's live panel can actually run
concurrently with the scheduler — building it earlier would be testing against a scenario that
doesn't exist yet). **31** ("unattended-run reliability") really only needs 28a+28b, not the
interactive pieces — it could start before 28c/28d/28e finish if that's useful. **29** (the panel
itself) needs all five.

## 7. Half B — ~~deferred, with its defects on record~~ **done 2026-08-10**

Was deferred until the Half A panel demonstrated you actually wanted persistent memory — it did,
and all five pieces below shipped as tasks 33–37 (see §7.1's breakdown table for what actually got
built, with real live-verification traces in each task doc). Left as-is below for the historical
record of what the v1 design got wrong and why reviving it needed real fixes first, not a redo of
the same mistakes.

**Kept from Half B, because it's nearly free — this is Half A's task 32.** A **zero-ceremony
free-text "why I own this"** note per holding: one nullable column, one input on the holdings
row. No structured invalidation conditions, no horizon fields, no re-scoring ritual. It costs
almost nothing, demands no discipline, and quietly accumulates the only data that makes drift
detection possible later. **Its consumer is the panel (task 29)**, which reads the notes so the
agent can reason about *why* you own something — so it's never write-only. The expensive,
rot-prone apparatus is what's deferred — not the habit of jotting a reason.

**Deferred, and what must be fixed first:**
- **`decision_log` grading is unbuildable as specified.** Nothing computes `outcome`; the v1
  task only *surfaced* it. Before reviving: add `reference_price`, `horizon`,
  `success_criterion`, `status(accepted|dismissed|expired)`, and FKs to holding/thesis —
  **captured at call time**, or no later job can grade fairly. Then build an actual grading job
  with per-call-type outcome definitions. Note the confounds: a *dismissed* call needs a
  counterfactual; an *accepted* one is muddied once you act manually in the broker.
- **`thesis` must be append-only/versioned** — a single mutable row can't represent scale-ins
  or an evolving view.
- **`conviction` must be historized** — an untimestamped score freezes at whatever was first
  typed and can never demonstrate the calibration the reframe wants.
- **Memory-poisoning is a durable write, not a rejectable suggestion.** If memory is read on
  every run, one poisoned run biases all subsequent output. Requires run-provenance tags on
  every row and quarantine of writes from runs that touched untrusted web content (§2.3).
- **Agent-authored desk note** (ranked reasoning replacing task 27's deterministic content) and
  the **behavioral mirror** (pattern detection over `trades`, sourced from task 21's Trade Book
  import) land here too — the mirror needs only task 21 + a surface, not the desk-note
  generator. PaytmMoney-only, same as the rest of the trade-history-dependent work (see the
  2026-07-23 update).

## 7.1 Half B breakdown (added 2026-08-09)

Task 32 (holding notes) already shipped as part of Half A — it's the cheap tier of this same idea
and stays as-is. The remaining §7 apparatus is decomposed into five sequenced task docs, numbered
33–37, written out in full (Depends-on/Scope/Out-of-scope/Acceptance-criteria) in
`docs/tasks/33-thesis-conviction.md` through `docs/tasks/37-behavioral-mirror.md`, per the same
standard as every task so far — real design decisions resolved in the doc itself, not left as open
questions for implementation time to discover.

| # | Task | Depends on | Notes |
|---|---|---|---|
| 33 | ~~Thesis + conviction (versioned, historized)~~ — **done 2026-08-10** | 29 | Foundational; coexists with (doesn't replace) task 32's `Holding.notes`. Agent-only via `add_thesis_entry`/`get_thesis_history`, no new page |
| 34 | ~~Decision log with real grading~~ — **done 2026-08-10** | 33 | Grades **call quality** (was the prediction right against real prices), not user outcome — the plan's own confound made this scope call explicit rather than left muddied. Grading is on-demand (`POST /api/decisions/grade`), not scheduler-driven, per task 25's real INDmoney rate-limit finding |
| 35 | ~~Memory-poisoning defenses~~ — **done 2026-08-10** | 33, 34 | Provenance tags (`run_session_id`, `touched_untrusted_content`) + sticky, human-only quarantine lift on both new tables. Ties into task 28c's WS loop and invariant #3 (task 28e). **Two real bugs found and fixed live**: `BaseHTTPMiddleware` silently doesn't propagate contextvars into the wrapped app's task (switched to plain ASGI middleware); a genuine same-turn race between a web-tool call and a write-tool call, closed with a post-turn reconciliation pass |
| 36 | ~~Agent-authored desk note~~ — **done 2026-08-10** | 33, 35, 27, 28a | **Augments**, never replaces, task 27's guaranteed-send deterministic digest — a best-effort second section with a 150s budget, dropped silently on failure/timeout. Verified with real SMTP sends both ways (agent section present and forced-absent) |
| 37 | ~~Behavioral mirror~~ — **done 2026-08-10** | 21 | Fully independent of 33–36 — only needs the Trade Book import. Three concrete patterns (disposition effect, averaging-down frequency, win/loss asymmetry) over real `Trade`/`RealizedGain` data, agent-only |

**33–37 done 2026-08-10.**

Sequence: **33 → 34 → 35 → 36** is a real dependency chain (thesis before decision-log before
quarantine before the desk note that should read quarantine-aware from day one). **37** has no
dependency on any of the other four and can be built and shipped whenever, before or after the
rest of this chain — the plan already called this out (§7) as the one piece buildable on its own.

## 8. Cut

- **IPO radar / GMP.** Lowest value, highest maintenance, most ToS-exposed: GMP exists only on
  third-party aggregators with no API, hostile terms, changing layouts, and the number itself is
  unofficial and manipulable. Novelty in an app about portfolio *discipline*. Cut rather than
  caveated.

## 9. Explicit non-goals

- No order execution, ever (invariant #1).
- No auto-applying anything to your broker — every output is a suggestion you perform manually.
- No unattended automation that requires handling your OTP or storing broker login credentials.
- No backfill of price history into our DB — OHLC is fetched on demand (India-only, §3).
- No multi-user, no cloud, no hosted deployment.
- No F&O tooling — option-chain/Greeks exist in the MCP but are out of scope for a cash-equity
  investor.
- No INDmoney tradebook/tax ingestion this phase (explicit decision, 2026-07-23). Tax
  suggestions, opportunity-cost, and the behavioral mirror are **PaytmMoney-only** — an INDmoney
  holding would simply not appear in those specific features. The INDmoney MCP pillars
  (whole-net-worth, live prices, OHLC) are unrelated and unaffected.

## 10. Open items

1. ~~**Tradebook format**~~ — **resolved 2026-07-23** by task 20 (§6). PaytmMoney only; see the
   findings there and the rescope in §5.1.
2. **Analyst add-on** — can INDmoney's analyst-consensus add-on be enabled on your account? It
   would give structured target-price numbers to complement web-sourced narrative. Not blocking.
3. **`.env` hardening** — recommend `chmod 600` and relocating it outside any agent working
   directory before task 28 ships.
4. **If INDmoney tradebook/tax data is ever wanted later**, task 21 will need a second parser
   for whatever format INDmoney exports (unknown — not investigated, per the 2026-07-23 scope
   decision), and tasks 22/behavioral-mirror will need to merge two brokers' realized-gains data
   rather than trusting one broker's pre-computed lot matching alone.
