# 13 — Frontend Scaffold & API Client

**Depends on:** —
**Unlocks:** 14, 15, 16, 17, 18

## Goal

A running Vite+React+TypeScript app with the visual foundation, routing, and a typed
API client already in place, so every later task is just filling in a page — not also
inventing project structure, styling, or fetch boilerplate each time.

## Scope

`deck-app/` (Vite + React + TypeScript, per architecture.md's Stack section):
- Routing: `react-router-dom`, 4 routes — `/` (Dashboard), `/manual-holdings`,
  `/thresholds`, `/status`. Small, fixed page set with no deep-linking need beyond
  "which page" — react-router's `BrowserRouter` is still the right call over hand-rolled
  nav state, since proper URL/back-button support is standard, expected behavior for a
  "real" app and costs nothing extra here.
- Data fetching: `@tanstack/react-query`. Justification: several later tasks need
  refetch-after-mutation (add a manual holding → dashboard numbers change; set a
  threshold → risk/alerts change) — query invalidation handles this cleanly instead of
  hand-rolling refetch logic on every page.
- `src/api/client.ts` — typed fetch wrappers for every bridge-server endpoint. Base URL
  from an env var (`VITE_API_BASE_URL`, default `http://localhost:8000`) — **no dev
  proxy needed**, `bridge-server`'s CORS is already configured for
  `http://localhost:5173` (Vite's default port) specifically for this, from task 1.
  One TypeScript type per response shape, matching `bridge-server/app/schemas/`
  field-for-field (not architecture.md's original sketch, which undershoots several of
  these — e.g. `DashboardOut.total_pnl_abs_inr`/`total_pnl_pct`, `TrajectoryOut`'s full
  field set including `recent_days`/`thirty_day_days`). Endpoints to wrap: `GET
  /api/dashboard`, `GET /api/trend`, `GET /api/alerts`, `GET /api/risk`, `GET/PUT
  /api/settings/risk`, `GET /api/thresholds`, `POST/PUT /api/thresholds`, `DELETE
  /api/thresholds`, `POST/PUT/DELETE /api/holdings/manual`, `POST
  /api/holdings/manual/import-csv`, `GET /api/status`, `POST /api/refresh`.
- Base layout: left nav + main content shell. **Port the UI prototype's existing design
  system** (`docs/ui-flow-prototype.html`'s `<style>` block — CSS custom properties,
  typography, color coding: green gain / red loss / amber threshold-proximity) into
  real component structure. That design was already built and reviewed; this task
  reuses it rather than re-deciding colors/type/spacing from scratch.

## Out of scope

- No production deployment config beyond Vite's default `npm run build` — local-only
  app, per planning.md.
- No auth — single-user local app, matches the backend's lack of auth entirely.
- No actual page content yet (tasks 14–18) — routes can render placeholders.

## Acceptance criteria

- `npm run dev` starts, all 4 routes render and are reachable via the left nav.
- The API client successfully calls `GET /api/health` against a running `bridge-server`
  and the result is visible somewhere in the UI (end-to-end wiring smoke test before
  any real page gets built).
- Colors, typography, and nav styling visibly match `ui-flow-prototype.html` side by
  side — not a fresh redesign.
