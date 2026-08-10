# 16 — Manual Holdings Page

**Depends on:** 13
**Unlocks:** —

## Goal

The UI for the write path task 10 built — adding, editing, deleting, and bulk-CSV-
importing the US holdings that INDmoney's API doesn't expose (Key Decision #1,
planning.md).

## Scope

`deck-app/src/pages/ManualHoldings.tsx`:
- **Add-holding form** — `symbol`, `quantity`, `avg_cost` (USD), `sector`, `exchange`
  (default `"NASDAQ"`) → `POST /api/holdings/manual`. Surface a clear message on `409`
  (symbol already exists) — the backend rejects duplicates outright, not silently.
- **Current manual holdings table.** There is **no standalone list endpoint** for
  these — derive it by filtering `GET /api/dashboard`'s `holdings` for
  `source === 'manual'`. Don't build or expect a `GET /api/holdings/manual` that
  doesn't exist.
- **Edit** — `PUT /api/holdings/manual/{id}`. The form must make the `ltp` field's
  behavior obvious: **omitting it preserves the holding's current price**; only
  provide it when actually repricing (task 10's reviewed behavior). Don't default the
  edit form to always resubmitting a stale/blank `ltp` — either omit it from the
  payload when unchanged, or clearly label it as "update current price" separate from
  quantity/avg_cost so the distinction is visible to the user, not just internal.
- **Delete** → `DELETE /api/holdings/manual/{id}`.
- **CSV import** — paste box + "Preview" step (client-side, mirrors the UI prototype's
  existing preview flow) before calling `POST /api/holdings/manual/import-csv`, then
  render the response's `imported` (list of `HoldingOut`) vs `skipped` (list of
  `{line_number, raw, reason}`) — show every skip reason, don't just report a count.

## Out of scope

- No live symbol validation (e.g. confirming a ticker is real) — matches task 10's own
  explicit scope, trust the input.

## Acceptance criteria

- Create/edit/delete are all immediately reflected on this page and on the Dashboard
  (task 14/15) via query invalidation — no manual reload needed.
- A CSV paste with intentionally malformed lines (missing a field, non-numeric qty)
  shows the specific skip reason per line, and still imports the valid lines in the
  same batch.
- Attempting to create a holding with a symbol that already exists surfaces the
  backend's `409` as a clear message, not a generic "request failed."
- Editing quantity/avg_cost without touching price leaves the holding's `ltp`
  unchanged on the next fetch — verified against the real backend, not assumed.
