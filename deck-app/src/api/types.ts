// Mirrors bridge-server/app/schemas/ field-for-field — the real, as-implemented
// API surface, not architecture.md's original sketch (which undershoots several
// of these). Keep in sync with the Pydantic schemas if either side changes.

export interface TrajectoryOut {
  cold_start: boolean;
  static: boolean;
  days_available: number | null;
  recent_days: number | null;
  recent_return_pct: number | null;
  thirty_day_days: number | null;
  thirty_day_return_pct: number | null;
  flag_kind: string | null;
  flag_text: string | null;
}

export interface DashboardHolding {
  id: number;
  broker: string;
  symbol: string;
  exchange: string;
  isin: string | null;
  quantity: number;
  avg_cost: number;
  ltp: number;
  close_price: number | null;
  currency: string;
  market_value: number;
  market_value_inr: number;
  pnl_abs: number;
  pnl_pct: number;
  sector: string | null;
  asset_class: string;
  source: string;
  notes: string | null;
  pricing: string;
  today_move_abs_inr: number | null;
  today_move_pct: number | null;
  threshold_breached: boolean;
  trajectory: TrajectoryOut;
}

export interface BreakdownItem {
  label: string;
  value_inr: number;
  pct: number;
}

export interface DashboardOut {
  net_worth_inr: number;
  today_move_abs_inr: number;
  today_move_pct: number;
  total_pnl_abs_inr: number;
  total_pnl_pct: number;
  breakdowns: Record<string, BreakdownItem[]>;
  holdings: DashboardHolding[];
}

export interface TrendPoint {
  captured_at: string;
  total_net_worth_inr: number;
}

export interface TrendOut {
  points: TrendPoint[];
}

export interface AlertItem {
  kind: string; // "stop_loss" | "mover"
  broker: string;
  symbol: string;
  severity: string; // "gain" | "loss"
  title: string;
}

export interface AlertsOut {
  alerts: AlertItem[];
}

export interface ConcentrationFlag {
  kind: string; // "stock" | "sector"
  label: string;
  pct: number;
  limit_pct: number;
}

export interface RegionSplit {
  india_pct: number;
  us_pct: number;
  target_india_pct: number | null;
  target_us_pct: number | null;
  drift_pct: number | null;
}

export interface RiskOut {
  concentration_flags: ConcentrationFlag[];
  region_split: RegionSplit;
}

export interface RiskSettingsOut {
  concentration_stock_pct: number;
  concentration_sector_pct: number;
  target_india_pct: number | null;
  target_us_pct: number | null;
}

export interface RiskSettingsIn {
  concentration_stock_pct?: number;
  concentration_sector_pct?: number;
  target_india_pct?: number;
  target_us_pct?: number;
}

export interface ThresholdListItem {
  broker: string;
  symbol: string;
  stop_loss_pct: number | null;
  target_pct: number | null;
  notes: string | null;
}

export interface ThresholdsListOut {
  thresholds: ThresholdListItem[];
}

export interface ThresholdOut {
  id: number;
  broker: string;
  symbol: string;
  stop_loss_pct: number | null;
  target_pct: number | null;
  notes: string | null;
}

export interface ThresholdIn {
  broker: string;
  symbol: string;
  stop_loss_pct?: number | null;
  target_pct?: number | null;
  notes?: string | null;
}

export interface HoldingOut {
  id: number;
  broker: string;
  symbol: string;
  exchange: string;
  isin: string | null;
  quantity: number;
  avg_cost: number;
  ltp: number;
  close_price: number | null;
  currency: string;
  market_value: number;
  market_value_inr: number;
  pnl_abs: number;
  pnl_pct: number;
  sector: string | null;
  asset_class: string;
  source: string;
  last_synced_at: string | null;
  notes: string | null;
}

export interface HoldingNotesIn {
  notes: string | null;
}

export interface ManualHoldingIn {
  symbol: string;
  quantity: number;
  avg_cost: number;
  sector?: string | null;
  exchange?: string;
  // Create: omit for a fresh baseline priced at avg_cost.
  // Edit: omit to keep the current price unchanged.
  ltp?: number | null;
}

export interface CsvImportSkippedRow {
  line_number: number;
  raw: string;
  reason: string;
}

export interface CsvImportOut {
  imported: HoldingOut[];
  skipped: CsvImportSkippedRow[];
}

export interface BrokerStatus {
  broker: string;
  mode: string; // "live" | "mock"
  last_sync_at: string | null;
  healthy: boolean;
  warning: string | null;
}

export interface StatusOut {
  brokers: BrokerStatus[];
}

// Task 35 — memory-poisoning defenses. A row here touched untrusted web
// content and hasn't been human-reviewed yet; it's already omitted from
// every agent-facing read by default (get_thesis_history/get_decisions),
// this is purely the human review surface.
export interface QuarantinedThesis {
  id: number;
  broker: string;
  symbol: string;
  text: string;
  conviction: number | null;
  run_session_id: string;
  created_at: string;
}

export interface QuarantinedDecision {
  id: number;
  broker: string;
  symbol: string;
  headline: string;
  run_session_id: string;
  created_at: string;
}

export interface QuarantineOut {
  theses: QuarantinedThesis[];
  decisions: QuarantinedDecision[];
}

export interface QuarantineReviewOut {
  table: string;
  id: number;
  reviewed: boolean;
}

export interface BrokerSyncResult {
  ok: boolean;
  count: number | null;
  error: string | null;
}

export interface RefreshOut {
  results: Record<string, BrokerSyncResult>;
}
