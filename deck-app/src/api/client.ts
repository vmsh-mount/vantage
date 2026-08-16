import type {
  AlertsOut,
  AllocationDimension,
  AllocationProgressOut,
  AllocationTargetIn,
  AllocationTargetOut,
  AllocationTargetsListOut,
  CsvImportOut,
  DashboardOut,
  DimensionBreakdownOut,
  DividendIn,
  DividendOut,
  DividendsListOut,
  GoalIn,
  GoalOut,
  GoalProgressOut,
  GoalsListOut,
  HoldingNotesIn,
  HoldingOut,
  ManualHoldingIn,
  MilestoneIn,
  MilestoneOut,
  MilestoneProgressOut,
  MilestonesListOut,
  QuarantineOut,
  QuarantineReviewOut,
  RefreshOut,
  RiskOut,
  RiskSettingsIn,
  RiskSettingsOut,
  StatusOut,
  ThresholdIn,
  ThresholdOut,
  ThresholdsListOut,
  TrendOut,
} from './types';

// No dev proxy needed — bridge-server's CORS is already configured for Vite's
// default port (task 1, CORS_ORIGIN=http://localhost:5173).
//
// 127.0.0.1, not localhost: "localhost" can resolve to ::1 first and hit an
// unrelated service bound to that port's IPv6 wildcard instead of bridge-server
// (which only binds 127.0.0.1). See .env.example.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function extractErrorMessage(body: unknown): string | null {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      // FastAPI/Pydantic 422 validation errors: [{loc, msg, type}, ...]
      return detail
        .map((entry) => (entry && typeof entry === 'object' && 'msg' in entry ? String(entry.msg) : JSON.stringify(entry)))
        .join('; ');
    }
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Only send Content-Type when there's actually a body — a bodyless GET/DELETE
  // with this header set becomes a non-"simple" CORS request, forcing an
  // unnecessary preflight for the majority of calls this client makes.
  const headers = init?.body
    ? { 'Content-Type': 'application/json', ...(init?.headers ?? {}) }
    : init?.headers;
  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, extractErrorMessage(body) ?? response.statusText);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),

  dashboard: () => request<DashboardOut>('/api/dashboard'),
  trend: (days = 30) => request<TrendOut>(`/api/trend?days=${days}`),
  alerts: () => request<AlertsOut>('/api/alerts'),
  risk: () => request<RiskOut>('/api/risk'),

  riskSettings: () => request<RiskSettingsOut>('/api/settings/risk'),
  updateRiskSettings: (payload: RiskSettingsIn) =>
    request<RiskSettingsOut>('/api/settings/risk', { method: 'PUT', body: JSON.stringify(payload) }),

  thresholds: () => request<ThresholdsListOut>('/api/thresholds'),
  createThreshold: (payload: ThresholdIn) =>
    request<ThresholdOut>('/api/thresholds', { method: 'POST', body: JSON.stringify(payload) }),
  updateThreshold: (payload: ThresholdIn) =>
    request<ThresholdOut>('/api/thresholds', { method: 'PUT', body: JSON.stringify(payload) }),
  deleteThreshold: (broker: string, symbol: string) =>
    request<void>(`/api/thresholds?broker=${encodeURIComponent(broker)}&symbol=${encodeURIComponent(symbol)}`, {
      method: 'DELETE',
    }),

  updateHoldingNotes: (id: number, payload: HoldingNotesIn) =>
    request<HoldingOut>(`/api/holdings/${id}/notes`, { method: 'PUT', body: JSON.stringify(payload) }),

  createManualHolding: (payload: ManualHoldingIn) =>
    request<HoldingOut>('/api/holdings/manual', { method: 'POST', body: JSON.stringify(payload) }),
  updateManualHolding: (id: number, payload: ManualHoldingIn) =>
    request<HoldingOut>(`/api/holdings/manual/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteManualHolding: (id: number) => request<void>(`/api/holdings/manual/${id}`, { method: 'DELETE' }),
  importCsv: (csv: string) =>
    request<CsvImportOut>('/api/holdings/manual/import-csv', { method: 'POST', body: JSON.stringify({ csv }) }),

  status: () => request<StatusOut>('/api/status'),
  refresh: () => request<RefreshOut>('/api/refresh', { method: 'POST' }),

  quarantine: () => request<QuarantineOut>('/api/quarantine'),
  reviewQuarantined: (table: string, id: number) =>
    request<QuarantineReviewOut>(`/api/quarantine/${table}/${id}/review`, { method: 'POST' }),

  // ---------- Compass ----------
  dividends: () => request<DividendsListOut>('/api/dividends'),
  createDividend: (payload: DividendIn) =>
    request<DividendOut>('/api/dividends', { method: 'POST', body: JSON.stringify(payload) }),
  deleteDividend: (id: number) => request<void>(`/api/dividends/${id}`, { method: 'DELETE' }),

  allocationTargets: (dimension?: AllocationDimension) =>
    request<AllocationTargetsListOut>(`/api/allocation-targets${dimension ? `?dimension=${dimension}` : ''}`),
  createAllocationTarget: (payload: AllocationTargetIn) =>
    request<AllocationTargetOut>('/api/allocation-targets', { method: 'POST', body: JSON.stringify(payload) }),
  deleteAllocationTarget: (id: number) => request<void>(`/api/allocation-targets/${id}`, { method: 'DELETE' }),
  allocationProgress: (dimension: AllocationDimension) =>
    request<AllocationProgressOut>(`/api/allocation-targets/progress?dimension=${dimension}`),
  allocationCurrentBreakdown: (dimension: AllocationDimension) =>
    request<DimensionBreakdownOut>(`/api/allocation-targets/current-breakdown?dimension=${dimension}`),

  milestones: () => request<MilestonesListOut>('/api/milestones'),
  createMilestone: (payload: MilestoneIn) =>
    request<MilestoneOut>('/api/milestones', { method: 'POST', body: JSON.stringify(payload) }),
  deleteMilestone: (id: number) => request<void>(`/api/milestones/${id}`, { method: 'DELETE' }),
  milestonesProgress: () => request<MilestoneProgressOut[]>('/api/milestones/progress'),

  goals: () => request<GoalsListOut>('/api/goals'),
  createGoal: (payload: GoalIn) => request<GoalOut>('/api/goals', { method: 'POST', body: JSON.stringify(payload) }),
  deleteGoal: (id: number) => request<void>(`/api/goals/${id}`, { method: 'DELETE' }),
  goalsProgress: () => request<GoalProgressOut[]>('/api/goals/progress'),
};
