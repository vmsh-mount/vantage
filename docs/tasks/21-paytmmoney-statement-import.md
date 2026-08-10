# 21 — PaytmMoney Statement Import

**Depends on:** 20 (Phase 2 tradebook schema spike — done 2026-07-23, see planning-phase2.md §6)
**Unlocks:** 22 (tax suggestions), opportunity-cost, behavioral mirror — all Phase 2

## Goal

The trade-history foundation for Phase 2. Task 20 pulled and inspected three real PaytmMoney
exports and found PaytmMoney already does the hard part (FIFO lot-matching, ST/LT
classification, harvesting math) — this task just gets that data into our DB, normalized, so
later tasks can build on it instead of re-deriving it.

**PaytmMoney only.** INDmoney tradebook/tax ingestion is explicitly out of scope this phase
(user decision, 2026-07-23) — INDmoney MCP-backed features (net worth, live prices, OHLC) are
unrelated and unaffected.

**Backend only.** No frontend upload page — files are provided via direct API call (multipart
upload) for now, matching "occasional, user-initiated, not daily" from the plan. A minimal
upload UI can be added later if the workflow proves annoying; not blocking task 22.

## Scope

Three real export formats, verified in task 20 against actual downloads — column names below
are exact, not guessed:

**1. Trade Book (`.xlsx`)** — immutable event log, **incremental/append**.
- Sheet `sheet`: a metadata block (UCC, Name, PAN, Period) then a blank row then the real
  header: `Date, Script, ISIN, Exchange, Product Type, Type, Quantity, Price, Brokerage, ETT,
  GST, STT, SEBI, Stamp Duty, Order Number, Trade Number, Trade Time`.
- **`Script` is PaytmMoney's internal numeric security code, not a ticker** — joins to our
  `Holding`/`Threshold` rows via **ISIN**, not symbol.
- **Dedup key: `(broker, order_number)`.** `Trade Number` was `'0'` on every real sample row —
  not usably unique — while `Order Number` was unique per execution. Re-uploading an
  overlapping date range must not duplicate rows.
- New model `Trade`: broker, trade_date, script_code, isin, exchange, product_type, txn_type
  (`BUY`/`SELL`), quantity, price, brokerage, ett, gst, stt, sebi, stamp_duty, order_number
  (unique with broker), trade_number, trade_time (nullable — blank on some real rows),
  imported_at.

**2. Tax P&L Statement (`.xlsx`)** — broker-recomputed snapshot, **replace-on-import** keyed by
`(broker, financial_year)`.
- Multi-sheet (`Summary, Equity, F&O, Mutual Fund - Equity, Mutual Fund - Debt, Open Positions
  …`) — **only the `Equity` sheet is in scope** ("stocks reports," per user).
- `Equity` sheet has three sections in one sheet (`Intraday Net Profit`, `Short-Term Net
  Profit`, `Long-Term Net Profit`), each its own mini-table: a section-label row, then a header
  row (`Quarter, Scrip Name, ISIN, Quantity, Buy Date, Buy Price, Buy Value, Sell Date, Sell
  Price, Sell Value, Net Realized P&L, Brokerage, Service Tax, STT, ETT, SEBI Tax, Stamp Duty,
  Total Charges & Tax`), data rows (already lot-matched — confirmed against real data with lots
  bought in 2021–2022 correctly classified long-term), then a `Total` row. Parse by scanning for
  the three known section labels rather than assuming fixed row numbers (row offsets differ
  when a section is empty, e.g. Intraday was empty in the real sample).
- New model `RealizedGain`: broker, financial_year, term (`intraday`/`short_term`/`long_term`),
  quarter, scrip_name, isin, quantity, buy_date, buy_price, buy_value, sell_date, sell_price,
  sell_value, net_realized_pnl, brokerage, service_tax, stt, ett, sebi_tax, stamp_duty,
  total_charges, imported_at.
- Import replaces: delete existing `RealizedGain` rows for `(broker, financial_year)`, insert
  fresh.

**3. Tax Gain/Loss Harvesting Report (`.xls`, legacy binary — needs `xlrd`, not `openpyxl`)** —
broker-recomputed snapshot, **replace-on-import** keyed by `(broker, as_on_date)`.
- Two sheets: `Tax Loss Harvesting` (ST/LT realized+unrealized summary, then a `Short Term
  Gains Offsetting` holdings table, then a `Long Term Gains Offsetting` holdings table) and
  `Tax Gain Harvesting` (LTCG summary, then a `Long Term Gains Opportunity` holdings table).
- Each holdings table shares one header shape: `Name, ISIN, Quantity, Buy Avg, Buy Value,
  Closing Price, Present Value, Unrealized P&L` — **no buy date** (that's why Trade Book is
  still needed for opportunity-cost, not this report).
- Summary rows are `(label, ..., 'Realised'|'Unrealised', amount, explanation, ...)` pairs —
  parse by matching the known labels (`Short Term Capital Gains - STCG`, `Short Term Capital
  Losses - STCL`, `Long Term Capital Gains - LTCG`, `Long Term Capital Losses - LTCL`) plus the
  two `*harvesting opportunity` amount rows and the `Tax Gain Harvesting Opportunity` amount row.
- New model `HarvestingPosition`: broker, as_on_date, kind
  (`loss_offset_short_term`/`loss_offset_long_term`/`gain_opportunity_long_term`), scrip_name,
  isin, quantity, buy_avg, buy_value, closing_price, present_value, unrealized_pnl, imported_at.
- New model `HarvestingSummary`: broker, as_on_date, financial_year, stcg_realized,
  stcl_unrealized, ltcg_realized, ltcl_unrealized, st_harvest_opportunity,
  lt_harvest_opportunity, lt_gain_harvest_opportunity, imported_at. One row per import.
- Import replaces: delete existing `HarvestingPosition`/`HarvestingSummary` rows for
  `(broker, as_on_date)`, insert fresh.

**Router** `bridge-server/app/routers/statements.py`:
- `POST /api/statements/tradebook` — multipart `.xlsx` upload → parse → dedupe-append → return
  `{imported: N, skipped: [{row, reason}]}` (same skip-reporting shape as task 10's CSV import).
- `POST /api/statements/tax-pnl` — multipart `.xlsx` upload → parse `Equity` sheet → replace →
  return `{financial_year, lots_imported, previous_lots_replaced}`.
- `POST /api/statements/harvesting` — multipart `.xls` upload → parse both sheets → replace →
  return `{as_on_date, positions_imported, previous_positions_replaced}`.

**New dependencies** (`requirements.txt`): `openpyxl` (`.xlsx`), `xlrd` (legacy `.xls`),
`python-multipart` (FastAPI file uploads — not currently installed, verified).

## Out of scope

- No FIFO/tax-lot computation, no timing suggestions, no LTCG-crossing-soon logic — that's
  task 22, which reads these tables but doesn't populate them.
- No frontend upload page (see Goal).
- No INDmoney statement parsing — different vendor, different (unknown) export format, would
  need its own task if pursued later (flagged in planning-phase2.md §10.4).
- No F&O / Mutual Fund sheet parsing from the Tax P&L Statement — equity only.
- No live symbol validation — trust the file, same posture as task 10.

## Acceptance criteria

- Uploading a real Trade Book file imports every row correctly, joined to our data via ISIN;
  re-uploading the same file (or one with overlapping rows) produces zero duplicates.
- Uploading a real Tax P&L Statement produces `RealizedGain` rows correctly split into
  short-term vs long-term, matching the file's own section totals; uploading a second file for
  the same financial year replaces rather than appends.
- Uploading a real Tax Gain/Loss Harvesting Report produces both the per-holding
  `HarvestingPosition` rows and the `HarvestingSummary` row, matching the file's own summary
  figures; a second upload for the same as-on-date replaces rather than appends.
- Verified against the real files already inspected in task 20 (re-requested from the user for
  this task, since the task-20 copies were deleted after the spike) — not just synthetic
  fixtures.
