# Vantage — Features

What you can actually do with the app, page by page, plus the two things that don't live on
a page at all (the agent panel and the daily email). See [architecture.md](./architecture.md)
for how any of this is built, and [mcp-tools.md](./mcp-tools.md) for the full agent-tool
reference.

## Dashboard

The default page. One consolidated view of PaytmMoney (India equity) + INDmoney (India + US
equity) holdings:

- **Net worth hero card** — total INR net worth, today's move (₹ and %), a 30-day trend
  sparkline.
- **Alerts** — today's threshold breaches and unusual daily movers, in one Tier-1 feed (the
  thing you'd otherwise open two apps to piece together).
- **Risk panel** — concentration flags (a single stock or sector over your configured
  limit) and India:US allocation drift against a target split, if you've set one.
- **Breakdown charts** — by broker, asset class, sector, India/US.
- **Holdings table** — every position, sortable, with a **Trajectory** column: 7d/30d
  return, a sparkline, and an occasional "unusual move" / "streak" / "near 30-day high-low"
  chip — the specific, computable answer to "is today's move actually unusual for *this*
  stock," not just a bare percentage. Rows within threshold distance are tinted amber.
  Manual (hand-entered) holdings show "Static — priced by you" instead of a Trajectory,
  since there's no live feed behind them.

## Manual Holdings

For US/other positions INDmoney's API doesn't expose. Add/edit/delete by hand, or paste a
CSV. These never get touched by the sync scheduler — price only moves when you edit it, by
design (there's no live feed to poll).

## Compass

Where you said you wanted to go, and how close you actually are — with real diagnosis when
you're not. Five sections (full design in [compass-prd.md](./compass-prd.md)):

- **Milestone** — a target reached by a date, not a recurring check (net worth by a date, or
  an overall P&L % target like "break even by March"), with a real pace projection from
  trailing portfolio history — never a guessed date.
- **Allocation targets** — a target % per bucket within a dimension (sector, asset class,
  region), checked against your real current allocation. A bucket at real 0% against a
  target is a named gap, not a missing checkmark; the add-target form shows your current %
  for a bucket as soon as you type/pick one.
- **Goals** — a single number checked against a target over a period: portfolio/sector/
  holding return %, dividend coverage (which trailing months had a logged dividend), or
  dividend amount vs. target.
- **Dividend log** — logged by hand (no broker API exposes this data) — the data source
  behind the two dividend goal types.
- **Risk controls** — guardrails, not goals: per-holding stop-loss %/target % (sign
  convention: stop-loss negative, target positive) plus the portfolio-wide risk settings
  (concentration limits, target India:US split) that drive the Dashboard's Risk panel. Moved
  in from the original standalone Thresholds page — same data, same endpoints, now living
  alongside the rest of what you set for yourself rather than on its own nav item. Purely
  local either way — setting a threshold here never touches your broker or places an order;
  you still execute it yourself.

## Status

Per-broker health (LIVE/MOCK badge, last sync time, a plain-language warning if a token's
expired or rejected), a manual "Refresh now" button, and a **Memory quarantine** section
(usually empty) — if an agent session that touched untrusted web content also wrote a
thesis/decision entry, it shows up here for one-click review before it can shape a future
answer. See [35-memory-poisoning-defenses.md](./tasks/35-memory-poisoning-defenses.md) for
why this exists.

## Ask Vantage (the agent panel)

A persistent side panel (open it from any page) backed by a real `claude` subprocess per
turn — not a canned FAQ bot. It can:

- **Answer questions about your real portfolio** — "what's my net worth," "am I
  overconcentrated in anything," "how has SWIGGY done vs. NIFTY," "what tax-loss harvesting
  opportunities do I have right now" — every number comes from a real tool call, shown
  inline as a tool card under the answer, never invented.
- **Search the web and cite it** — e.g. "why did GAIL drop today" pulls real news, always
  attributed, never blended into the numbers as if it were portfolio data.
- **Set stop-loss/target thresholds for you** — "set a 7% stop on SWIGGY" actually writes
  it; you still need to place the order yourself in the broker app.
- **Log an investment thesis** — "log my thesis on SWIGGY: bought after the delivery-volume
  beat, holding through FY27" appends a new, timestamped, never-overwritten entry. Ask
  "what's my thesis history on X" to see it evolve over time.
- **Log a concrete, checkable call** — "I think SWIGGY holds above ₹250 for the next 30
  days" can be logged as a real decision with a reference price and horizon; a later "grade
  my pending decisions" (via `POST /api/decisions/grade`, on demand) checks it against real
  market prices and records whether it was right — call quality, not whether you actually
  acted on it.
- **Describe your own trading patterns** — "what patterns do you see in how I trade" pulls
  disposition effect, averaging-down frequency, and win/loss asymmetry from your real
  PaytmMoney trade history.
- **Point at a holding in the UI** — the panel can scroll to and highlight a specific row
  while discussing it.

It **cannot**: place or modify any order, read your `.env`/credentials, or run arbitrary
shell commands — the subprocess is scoped down to exactly Vantage's own tools (see
[architecture.md's Security section](./architecture.md#security)). Every fact it states is
backed by a real, inspectable tool call — if you don't see a tool card, treat the claim
skeptically.

## Daily digest email

One email a day (07:00 IST by default, configurable), composed and sent **entirely in
Python** — no agent dependency, so it sends regardless of whether Claude Code or INDmoney is
reachable that day. Leads with anything genuinely urgent (stop-loss hits, LTCG windows
closing soon), then tax opportunities, concentration flags, big movers, and a one-line
summary. If the *previous* day's send failed or didn't happen, today's email leads with a
plain warning instead of failing silently.

On top of that guaranteed content, most days it also includes an **"Agent's take"** section
— a short, ranked, best-effort commentary written by a real agent turn (with web access, so
it can cite real news), clearly separated from the deterministic content above it. If that
turn fails, times out (150s budget), or errors, the section is just absent — the rest of the
email is unaffected either way.

## Trade/tax statement import

Upload PaytmMoney's own Trade Book, Tax P&L Statement, and Tax Gain/Loss Harvesting Report
exports (`.xlsx`/`.xls`, via `POST /api/statements/*`) to unlock: tax suggestions, the
benchmark-vs-NIFTY feature, and the behavioral mirror — all PaytmMoney-only, since INDmoney
has no equivalent export.

## What's intentionally not here

- No order placement of any kind, anywhere, for any broker.
- No INDmoney trade-history-dependent features (tax suggestions, benchmark, behavioral
  mirror) — INDmoney's API has no Trade Book equivalent.
- No mobile app, no multi-user support — this is a local, single-user tool.
- No IPO tracker / GMP feed — cut early, see [planning-phase2.md §8](./planning-phase2.md).

See [planning.md](./planning.md) and [planning-phase2.md](./planning-phase2.md) for the full
reasoning behind every scope call, and [tasks/](./tasks/) for exactly how each feature was
built and verified.
