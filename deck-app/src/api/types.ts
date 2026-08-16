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

// ---------- Compass (docs/compass-prd.md) ----------

export interface DividendIn {
  broker: string;
  symbol: string;
  amount_inr: number;
  payment_date: string;
  notes?: string | null;
}

export interface DividendOut {
  id: number;
  broker: string;
  symbol: string;
  amount_inr: number;
  payment_date: string;
  notes: string | null;
  created_at: string;
}

export interface DividendsListOut {
  dividends: DividendOut[];
}

export type AllocationDimension = 'sector' | 'asset_class' | 'region';

export interface AllocationTargetIn {
  dimension: AllocationDimension;
  bucket: string;
  target_pct: number;
  tolerance_pct?: number;
  rationale?: string | null;
}

export interface AllocationTargetOut {
  id: number;
  dimension: string;
  bucket: string;
  target_pct: number;
  tolerance_pct: number;
  rationale: string | null;
  active: boolean;
  created_at: string;
}

export interface AllocationTargetsListOut {
  targets: AllocationTargetOut[];
}

export interface AllocationProgressItem {
  id: number;
  dimension: string;
  bucket: string;
  target_pct: number;
  tolerance_pct: number;
  rationale: string | null;
  actual_pct: number;
  actual_value_inr: number;
  status: 'on_target' | 'underweight' | 'overweight';
  gap_pct: number;
  unmatched_bucket_names: string[];
}

export interface AllocationProgressOut {
  dimension: string;
  progress: AllocationProgressItem[];
}

export interface DimensionBreakdownItem {
  bucket: string;
  actual_pct: number;
  actual_value_inr: number;
}

export interface DimensionBreakdownOut {
  dimension: string;
  breakdown: DimensionBreakdownItem[];
}

export type MilestoneMetricType = 'net_worth' | 'pnl_pct';

export interface MilestoneIn {
  name: string;
  metric_type?: MilestoneMetricType;
  target_value: number;
  target_date: string;
  rationale?: string | null;
}

export interface MilestoneOut {
  id: number;
  name: string;
  metric_type: string;
  target_value: number;
  target_date: string;
  rationale: string | null;
  active: boolean;
  created_at: string;
}

export interface MilestonesListOut {
  milestones: MilestoneOut[];
}

export interface MilestoneProgressOut {
  id: number;
  name: string;
  metric_type: MilestoneMetricType;
  target_value: number;
  target_date: string;
  rationale: string | null;
  current_value: number | null;
  progress_pct: number | null;
  status: 'met' | 'on_pace' | 'behind' | 'not_enough_data';
  actual_pace_per_day: number | null;
  required_pace_per_day: number | null;
  projected_date: string | null;
  days_remaining: number | null;
  pace_window_days: number;
}

export type GoalScopeType = 'portfolio' | 'sector' | 'holding';
export type GoalMetricType = 'price_return_pct' | 'dividend_coverage' | 'dividend_amount';

export interface GoalIn {
  name: string;
  metric_type: GoalMetricType;
  target_value: number;
  scope_type?: GoalScopeType;
  scope_value?: string | null;
  comparison?: 'gte' | 'lte';
  period?: string;
  period_n?: number | null;
  rationale?: string | null;
}

export interface GoalOut {
  id: number;
  name: string;
  metric_type: string;
  scope_type: string;
  scope_value: string | null;
  comparison: string;
  target_value: number;
  period: string;
  period_n: number | null;
  rationale: string | null;
  active: boolean;
  created_at: string;
}

export interface GoalsListOut {
  goals: GoalOut[];
}

export interface GoalContribution {
  broker: string;
  symbol: string;
  start_value_inr: number;
  current_value_inr: number;
  return_pct: number;
  contribution_pp: number;
}

export interface GoalCoverageMonth {
  year: number;
  month: number;
  covered: boolean;
}

// The shape genuinely varies by metric_type — contributions only for
// price_return_pct, coverage/gap_months only for dividend_coverage,
// prior_period_total_inr only for dividend_amount. Optional fields, not a
// union, since every progress item shares the same base fields regardless.
export interface GoalProgressOut {
  id: number;
  name: string;
  metric_type: string;
  scope_type: string;
  scope_value: string | null;
  comparison: string;
  target_value: number;
  period: string;
  rationale: string | null;
  actual_value: number | null;
  status: 'met' | 'missed' | 'not_enough_data';
  period_start?: string;
  contributions?: GoalContribution[];
  window_months?: number;
  coverage?: GoalCoverageMonth[];
  gap_months?: string[];
  prior_period_total_inr?: number;
}

export interface CompassSummaryOut {
  goals: { total: number; met: number };
  allocation_targets: { total: number; on_target: number };
  milestones: { total: number; on_pace: number };
}
