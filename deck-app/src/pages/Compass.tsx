// Compass (docs/compass-prd.md) — goal-setting and diagnosis for the
// portfolio. Three shapes assembled into one page: Milestone (deadline),
// AllocationTarget (composition), Goal (scalar, incl. dividend metric
// types) — plus the raw Dividend log those last two read from, and Risk
// Controls (RiskControlsSection, moved in from the old standalone
// /thresholds page) — guardrails rather than targets, kept as their own
// section rather than reshaped into one of the three target shapes.
//
// Redesigned for density: an overview strip of progress rings replaces
// the old flat text tiles; Milestones/Goals render as one-line rows that
// expand on click instead of always-open cards; Allocation targets render
// as a single grouped chart per dimension instead of stacked full-width
// rails; and every "+ Add" form moved from an inline block (which used to
// push the whole page down) into a slide-over drawer.
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { PieChart, Pie, Cell, Tooltip } from 'recharts';
import { api, ApiError } from '../api/client';
import { RiskControlsSection } from '../components/RiskControlsSection';
import type {
  AllocationDimension,
  AllocationProgressItem,
  DashboardHolding,
  DividendOut,
  GoalMetricType,
  GoalProgressOut,
  GoalScopeType,
  MilestoneMetricType,
  MilestoneProgressOut,
} from '../api/types';
import { CHART_COLORS, fmtINR, fmtPct, fmtSigned } from '../lib/format';

// Pace values (rupees/day for net_worth, percentage points/day for
// pnl_pct) can be negative (shrinking net worth, worsening P&L) — always
// show the sign so "Why" reads as a trend, not just a bare magnitude.
function fmtPace(value: number, metricType: MilestoneMetricType): string {
  return metricType === 'pnl_pct' ? fmtPct(value) : fmtSigned(value);
}

const DIMENSIONS: { value: AllocationDimension; label: string }[] = [
  { value: 'sector', label: 'Sector' },
  { value: 'asset_class', label: 'Asset Class' },
  { value: 'region', label: 'Region' },
];

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Mirrors bridge-server/app/regions.py's region_for_exchange exactly — the
// only dimension whose bucket value isn't a plain holding field.
const US_EXCHANGES = new Set(['NASDAQ', 'NYSE']);
function regionForExchange(exchange: string): string {
  return US_EXCHANGES.has(exchange) ? 'us' : 'india';
}

function bucketValueFor(h: DashboardHolding, dimension: AllocationDimension): string | null {
  if (dimension === 'sector') return h.sector;
  if (dimension === 'asset_class') return h.asset_class;
  return regionForExchange(h.exchange);
}

// A target's bucket can name several real sector/asset-class/region values
// comma-separated (mirrors the backend's split_bucket_names) — a holding
// counts if its own value matches any segment, case-insensitively.
function holdingsForBucket(holdings: DashboardHolding[], dimension: AllocationDimension, bucket: string): DashboardHolding[] {
  const segments = bucket.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
  return holdings.filter((h) => {
    const v = bucketValueFor(h, dimension);
    return v != null && segments.includes(v.toLowerCase());
  });
}

function useErrorMessage() {
  const [error, setError] = useState<string | null>(null);
  return {
    error,
    setError,
    onError: (err: unknown, fallback: string) => setError(err instanceof ApiError ? err.message : fallback),
  };
}

// ============================================================
// Shared bits: drawer + status badge + ring
// ============================================================

function Drawer({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <>
      <div className="cx-drawer-backdrop" onClick={onClose} />
      <div className="cx-drawer" role="dialog" aria-modal="true" aria-label={title}>
        <div className="cx-drawer-head">
          <div>
            <p className="cx-drawer-title">{title}</p>
            {subtitle && <p className="cx-drawer-sub">{subtitle}</p>}
          </div>
          <button className="cx-drawer-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="cx-drawer-body">{children}</div>
      </div>
    </>
  );
}

function StatusBadge({ tone, children }: { tone: 'gain' | 'loss' | 'warn' | 'neutral'; children: React.ReactNode }) {
  return (
    <span className={`badge badge-${tone}`}>
      <span className="badge-dot" />
      {children}
    </span>
  );
}

// A small progress ring for the overview strip — circumference for r=20.
const RING_R = 20;
const RING_C = 2 * Math.PI * RING_R;

function Ring({ frac, tone }: { frac: number | null; tone: 'gain' | 'loss' | 'warn' | 'neutral' }) {
  const color = tone === 'neutral' ? 'var(--border)' : `var(--${tone === 'gain' ? 'gain' : tone === 'loss' ? 'loss' : 'warn'})`;
  const offset = frac == null ? RING_C : RING_C - Math.max(0, Math.min(1, frac)) * RING_C;
  return (
    <svg viewBox="0 0 48 48">
      <circle className="ov-ring-track" cx="24" cy="24" r={RING_R} />
      <circle className="ov-ring-fill" cx="24" cy="24" r={RING_R} stroke={color} strokeDasharray={RING_C} strokeDashoffset={offset} />
    </svg>
  );
}

// ============================================================
// Overview strip (replaces the old flat SummaryStrip)
// ============================================================

function buildSparklinePoints(values: number[], width = 120, height = 30): string {
  if (values.length === 0) return '';
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const stepX = values.length > 1 ? width / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

function OverviewStrip() {
  const goalsProgress = useQuery({ queryKey: ['goalsProgress'], queryFn: api.goalsProgress });
  const milestonesProgress = useQuery({ queryKey: ['milestonesProgress'], queryFn: api.milestonesProgress });
  const sectorProgress = useQuery({ queryKey: ['allocationProgress', 'sector'], queryFn: () => api.allocationProgress('sector') });
  const assetClassProgress = useQuery({ queryKey: ['allocationProgress', 'asset_class'], queryFn: () => api.allocationProgress('asset_class') });
  const regionProgress = useQuery({ queryKey: ['allocationProgress', 'region'], queryFn: () => api.allocationProgress('region') });
  const dividends = useQuery({ queryKey: ['dividends'], queryFn: api.dividends });

  const dividendRows = dividends.data?.dividends ?? [];
  const dividendTotal = dividendRows.reduce((sum, d) => sum + d.amount_inr, 0);

  const goals = goalsProgress.data ?? [];
  const goalsMet = goals.filter((g) => g.status === 'met').length;

  const allocationItems = [...(sectorProgress.data?.progress ?? []), ...(assetClassProgress.data?.progress ?? []), ...(regionProgress.data?.progress ?? [])];
  const onTarget = allocationItems.filter((i) => i.status === 'on_target').length;

  const milestones = milestonesProgress.data ?? [];
  const onPace = milestones.filter((m) => m.status === 'met' || m.status === 'on_pace').length;

  const ringTone = (met: number, total: number): 'gain' | 'loss' | 'warn' | 'neutral' =>
    total === 0 ? 'neutral' : met === total ? 'gain' : met === 0 ? 'loss' : 'warn';

  // Last 8 calendar months of dividend totals, oldest first — a quick
  // shape for "is this trending up", not a precise chart.
  const monthlySpark = useMemo(() => {
    const byMonth = new Map<string, number>();
    for (const d of dividendRows) {
      const key = d.payment_date.slice(0, 7);
      byMonth.set(key, (byMonth.get(key) ?? 0) + d.amount_inr);
    }
    const keys = [...byMonth.keys()].sort().slice(-8);
    return keys.map((k) => byMonth.get(k)!);
  }, [dividendRows]);

  return (
    <div className="overview">
      <div className="ov-tile">
        <div className="ov-ring-wrap">
          <Ring frac={goals.length ? goalsMet / goals.length : null} tone={ringTone(goalsMet, goals.length)} />
          <div className="ov-ring-num">{goals.length ? `${goalsMet}/${goals.length}` : '–'}</div>
        </div>
        <div>
          <p className="ov-label">Goals</p>
          <p className="ov-sub">
            {goals.length === 0 ? 'none set yet' : goalsMet === goals.length ? 'all on track' : <><strong>{goals.length - goalsMet}</strong> off track</>}
          </p>
        </div>
      </div>
      <div className="ov-tile">
        <div className="ov-ring-wrap">
          <Ring frac={allocationItems.length ? onTarget / allocationItems.length : null} tone={ringTone(onTarget, allocationItems.length)} />
          <div className="ov-ring-num">{allocationItems.length ? `${onTarget}/${allocationItems.length}` : '–'}</div>
        </div>
        <div>
          <p className="ov-label">Allocation</p>
          <p className="ov-sub">
            {allocationItems.length === 0 ? 'none set yet' : onTarget === allocationItems.length ? 'all on target' : <><strong>{allocationItems.length - onTarget}</strong> off target</>}
          </p>
        </div>
      </div>
      <div className="ov-tile">
        <div className="ov-ring-wrap">
          <Ring frac={milestones.length ? onPace / milestones.length : null} tone={ringTone(onPace, milestones.length)} />
          <div className="ov-ring-num">{milestones.length ? `${onPace}/${milestones.length}` : '–'}</div>
        </div>
        <div>
          <p className="ov-label">Milestones</p>
          <p className="ov-sub">
            {milestones.length === 0 ? 'none set yet' : onPace === milestones.length ? 'all on pace' : <><strong>{milestones.length - onPace}</strong> behind</>}
          </p>
        </div>
      </div>
      <div className="ov-div">
        <div>
          <p className="ov-label">Dividend log</p>
          <p className="ov-div-figure">
            {fmtINR(dividendTotal)}
            <span className="ov-div-of">{dividendRows.length} logged</span>
          </p>
        </div>
        {monthlySpark.length > 1 && (
          <svg width="120" height="30" viewBox="0 0 120 30" className="ov-spark">
            <polyline points={buildSparklinePoints(monthlySpark)} fill="none" stroke="var(--chart-1)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Milestones
// ============================================================

function MilestoneRow({ m }: { m: MilestoneProgressOut }) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteMilestone(m.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['milestonesProgress'] }),
  });

  const progressPct = m.progress_pct != null ? Math.min(100, Math.max(0, m.progress_pct)) : null;
  const tone = m.status === 'met' || m.status === 'on_pace' ? 'gain' : m.status === 'behind' ? 'loss' : 'neutral';
  const badgeText = { met: 'Met', on_pace: 'On pace', behind: 'Behind', not_enough_data: 'Not enough data' }[m.status];
  // progress_pct is null for pnl_pct by design (app/milestones.py's
  // _progress_pct docstring) — a percent-of-target ratio doesn't
  // generalize past net_worth, so there's no bar to fill for that type.
  const fmtValue = m.metric_type === 'pnl_pct' ? fmtPct : fmtINR;

  return (
    <div className={`item-row${expanded ? ' expanded' : ''}`} onClick={() => setExpanded((v) => !v)} role="button" tabIndex={0}>
      <div>
        <p className="item-name">{m.name}</p>
        <p className="item-meta">
          Target date {m.target_date}
          {m.days_remaining != null && ` · ${m.days_remaining >= 0 ? `${m.days_remaining} days away` : `${-m.days_remaining} days overdue`}`}
        </p>
      </div>
      <div>{progressPct != null && <div className="mini-track"><div className="mini-fill" style={{ width: `${progressPct}%`, background: 'var(--chart-1)' }} /></div>}</div>
      <div className="item-figs">
        {m.current_value != null ? (
          <>
            <span className={`item-cur mono tone-${tone}`}>{fmtValue(m.current_value)}</span>
            <span className="item-of">
              of {m.metric_type === 'pnl_pct' && m.target_value === 0 ? 'break even' : fmtValue(m.target_value)}
              {progressPct != null && ` · ${Math.round(m.progress_pct!)}%`}
            </span>
          </>
        ) : (
          <span className="item-of">no data yet</span>
        )}
      </div>
      <StatusBadge tone={tone}>{badgeText}</StatusBadge>
      <span className="item-chev">{expanded ? '▾' : '▸'}</span>

      {expanded && (
        <div className="item-detail" onClick={(e) => e.stopPropagation()}>
          {m.current_value == null ? (
            <p className="item-rationale">Not enough portfolio history yet to compute progress.</p>
          ) : (
            <div className="item-detail-stats">
              {m.status === 'met' ? (
                <div>
                  <p className="detail-stat-label">Status</p>
                  <p className="detail-stat-val tone-gain">Target reached</p>
                </div>
              ) : m.actual_pace_per_day != null ? (
                <>
                  <div>
                    <p className="detail-stat-label">Recent pace</p>
                    <p className={`detail-stat-val ${m.actual_pace_per_day >= 0 ? 'tone-gain' : 'tone-loss'}`}>
                      {fmtPace(m.actual_pace_per_day, m.metric_type)}/day
                    </p>
                  </div>
                  <div>
                    <p className="detail-stat-label">Needed pace</p>
                    <p className="detail-stat-val">
                      {m.required_pace_per_day != null ? `${fmtPace(m.required_pace_per_day, m.metric_type)}/day` : 'unknown'}
                    </p>
                  </div>
                  <div>
                    <p className="detail-stat-label">Projected</p>
                    <p className="detail-stat-val">
                      {m.projected_date ?? (m.actual_pace_per_day <= 0 ? "won't reach it" : 'unknown')}
                    </p>
                  </div>
                </>
              ) : (
                <div>
                  <p className="detail-stat-label">Recent trend</p>
                  <p className="detail-stat-val">
                    Not enough history in the last {m.pace_window_days} days
                    {m.required_pace_per_day != null && ` — needs ${fmtPace(m.required_pace_per_day, m.metric_type)}/day from here`}
                  </p>
                </div>
              )}
            </div>
          )}
          {m.rationale && <p className="item-rationale">{m.rationale}</p>}
          <div>
            <button className="btn btn-ghost btn-sm" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
              Remove
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const MILESTONE_METRIC_TYPES: { value: MilestoneMetricType; label: string }[] = [
  { value: 'net_worth', label: 'Net worth (₹)' },
  { value: 'pnl_pct', label: 'Overall P&L (%)' },
];

function MilestonesSection() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [metricType, setMetricType] = useState<MilestoneMetricType>('net_worth');
  const [targetValue, setTargetValue] = useState('');
  const [targetDate, setTargetDate] = useState('');
  const [rationale, setRationale] = useState('');
  const { error, setError, onError } = useErrorMessage();

  const progressQuery = useQuery({ queryKey: ['milestonesProgress'], queryFn: api.milestonesProgress });
  const milestones = progressQuery.data ?? [];
  const behindCount = milestones.filter((m) => m.status === 'behind').length;

  const createMutation = useMutation({
    mutationFn: () =>
      api.createMilestone({
        name,
        metric_type: metricType,
        target_value: Number(targetValue),
        target_date: targetDate,
        rationale: rationale.trim() || null,
      }),
    onSuccess: () => {
      setError(null);
      setShowForm(false);
      setName('');
      setMetricType('net_worth');
      setTargetValue('');
      setTargetDate('');
      setRationale('');
      queryClient.invalidateQueries({ queryKey: ['milestonesProgress'] });
    },
    onError: (err) => onError(err, 'Failed to create milestone.'),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    // net_worth needs a positive rupee target; pnl_pct can legitimately be
    // 0 (break-even) or negative (e.g. "cut the loss to -5%") — see
    // app/routers/milestones.py's own metric_type-conditional check.
    const targetOk = metricType === 'net_worth' ? Number(targetValue) > 0 : targetValue.trim() !== '' && !Number.isNaN(Number(targetValue));
    if (!name.trim() || !targetOk || !targetDate) {
      setError(
        metricType === 'net_worth'
          ? 'Name, a positive target amount, and a target date are all required.'
          : 'Name, a target P&L %, and a target date are all required.',
      );
      return;
    }
    createMutation.mutate();
  }

  return (
    <section className="card compass-section">
      <div className="section-head">
        <div className="section-title-row">
          <div>
            <h2 className="section-title">Milestones</h2>
            <p className="section-sub">A target reached by a date, not a recurring check</p>
          </div>
          {behindCount > 0 && <span className="section-flag">{behindCount} behind</span>}
        </div>
        <button className="section-add" onClick={() => setShowForm(true)}>+ Add milestone</button>
      </div>

      {showForm && (
        <Drawer title="Add milestone" subtitle="A target reached by a date, not a recurring check" onClose={() => setShowForm(false)}>
          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="field">
              <label>Metric</label>
              <select value={metricType} onChange={(e) => setMetricType(e.target.value as MilestoneMetricType)}>
                {MILESTONE_METRIC_TYPES.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Name</label>
              <input
                type="text"
                placeholder={metricType === 'pnl_pct' ? 'Break even' : 'Reach ₹50,00,000 net worth'}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="cx-field-row">
              <div className="field">
                <label>{metricType === 'pnl_pct' ? 'Target P&L (%)' : 'Target (₹)'}</label>
                <input
                  type="number"
                  step={metricType === 'pnl_pct' ? '0.1' : '1'}
                  placeholder={metricType === 'pnl_pct' ? '0' : '5000000'}
                  value={targetValue}
                  onChange={(e) => setTargetValue(e.target.value)}
                />
                {metricType === 'net_worth' && Number(targetValue) > 0 && <p className="hint">= {fmtINR(Number(targetValue))}</p>}
              </div>
              <div className="field">
                <label>Target date</label>
                <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label>Rationale (optional)</label>
              <textarea
                placeholder="Why this milestone? e.g. tuition due in mid-2027, want a real cushion above it."
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={3}
              />
            </div>
            {error && <p className="error-state" style={{ padding: 0 }}>{error}</p>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Saving…' : 'Save milestone'}
              </button>
            </div>
          </form>
        </Drawer>
      )}

      <div className="row-list">
        {progressQuery.isLoading && <p className="loading-state">Loading…</p>}
        {progressQuery.isError && <p className="error-state">Can't reach bridge-server.</p>}
        {milestones.length === 0 && !progressQuery.isLoading && <p className="footnote" style={{ margin: '0 20px 4px' }}>No milestones set yet.</p>}
        {milestones.map((m) => <MilestoneRow key={m.id} m={m} />)}
      </div>
    </section>
  );
}

// ============================================================
// Allocation targets
// ============================================================

function AllocationBucketRow({
  item,
  dimension,
  holdings,
}: {
  item: AllocationProgressItem;
  dimension: AllocationDimension;
  holdings: DashboardHolding[];
}) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteAllocationTarget(item.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['allocationProgress'] }),
  });

  const zoneLeft = Math.max(0, item.target_pct - item.tolerance_pct);
  const zoneWidth = item.tolerance_pct * 2;
  const actualClamped = Math.min(100, Math.max(0, item.actual_pct));
  const tone = item.status === 'on_target' ? 'gain' : item.actual_pct < item.target_pct - item.tolerance_pct * 2 ? 'loss' : 'warn';
  const bucketHoldings = useMemo(
    () => holdingsForBucket(holdings, dimension, item.bucket).sort((a, b) => b.market_value_inr - a.market_value_inr),
    [holdings, dimension, item.bucket],
  );
  const hasDetail = item.status !== 'on_target' || !!item.rationale || item.unmatched_bucket_names.length > 0 || bucketHoldings.length > 0;

  return (
    <div className={`alloc-row${expanded ? ' expanded' : ''}`} onClick={() => hasDetail && setExpanded((v) => !v)} role="button" tabIndex={0}>
      <span className="alloc-label">{item.bucket}</span>
      <div className="alloc-figs">
        <span className="actual" style={tone !== 'gain' ? { color: `var(--${tone})` } : undefined}>{item.actual_pct}%</span>
        <span className="target">target {item.target_pct}%</span>
      </div>
      <div className="alloc-track">
        <div className="rail-bg" />
        <div className="alloc-target-zone" style={{ left: `${zoneLeft}%`, width: `${zoneWidth}%` }} />
        <div className={`alloc-actual-fill tone-${tone}`} style={{ width: `${actualClamped}%` }} />
        <div className="alloc-marker" style={{ left: `${actualClamped}%` }} />
      </div>
      <span className="alloc-chev">{hasDetail ? (expanded ? '▾' : '▸') : ''}</span>

      {expanded && (
        <div className="alloc-row-detail" onClick={(e) => e.stopPropagation()}>
          {item.unmatched_bucket_names.length > 0 ? (
            // Real bug found via a user's own manual reconciliation against
            // the Dashboard: a typo'd bucket name (e.g. "QSR" vs the broker's
            // real "Quick Service Restaurant") used to silently read as an
            // indistinguishable, verified-looking 0% gap. This is the fix —
            // a distinct, unmissable warning whenever the name doesn't match
            // anything currently held, instead of a number that looks real
            // but might not be.
            <p className="alloc-gap-note tone-loss">
              ⚠ {item.unmatched_bucket_names.map((n) => `"${n}"`).join(', ')} — {item.unmatched_bucket_names.length === 1 ? "doesn't" : "don't"} match any
              of your current holdings' real {item.dimension} names. This number may be wrong, not a verified gap — check the
              exact spelling on the Dashboard's breakdown (or this may genuinely be something you don't hold yet).
            </p>
          ) : (
            item.status !== 'on_target' && (
              <p className={`alloc-gap-note ${tone === 'loss' ? 'tone-loss' : 'tone-warn'}`}>
                {item.actual_pct === 0
                  ? `No holding in this bucket at all — ${Math.abs(item.gap_pct).toFixed(1)}pp under target.`
                  : `${item.status === 'underweight' ? `${Math.abs(item.gap_pct).toFixed(1)}pp under` : `${Math.abs(item.gap_pct).toFixed(1)}pp over`} target.`}
              </p>
            )
          )}
          {item.rationale && <p className="why-note">{item.rationale}</p>}
          {bucketHoldings.length > 0 && (
            <div>
              <p className="why-block-title">How {item.bucket} breaks down · {fmtINR(item.actual_value_inr)} total</p>
              <div className="donut-body">
                <div className="donut-wrap">
                  <PieChart width={108} height={108}>
                    <Pie
                      data={bucketHoldings}
                      dataKey="market_value_inr"
                      nameKey="symbol"
                      cx="50%"
                      cy="50%"
                      innerRadius={32}
                      outerRadius={54}
                      startAngle={90}
                      endAngle={-270}
                      stroke="none"
                      isAnimationActive={false}
                    >
                      {bucketHoldings.map((h, i) => (
                        <Cell key={`${h.broker}:${h.symbol}`} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value) => fmtINR(Number(value))}
                      contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 11.5 }}
                      // Recharts defaults tooltip text to near-black — invisible
                      // against a dark-theme surface, which is exactly why
                      // hovering a slice looked like it showed nothing.
                      itemStyle={{ color: 'var(--text)' }}
                      labelStyle={{ color: 'var(--text)' }}
                    />
                  </PieChart>
                  <div className="donut-total">
                    <span className="donut-total-val mono">{fmtINR(item.actual_value_inr)}</span>
                    <span className="donut-total-label">total</span>
                  </div>
                </div>
                <div className="donut-legend">
                  {bucketHoldings.map((h, i) => {
                    const weightInBucket = item.actual_value_inr > 0 ? (h.market_value_inr / item.actual_value_inr) * 100 : 0;
                    return (
                      <div className="donut-legend-item" key={`${h.broker}:${h.symbol}`}>
                        <span className="donut-sw" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
                        <div className="donut-legend-body">
                          <span className="donut-name">{h.symbol}<span className="sub"> · {h.broker}</span></span>
                          <span className="donut-val mono">{fmtINR(h.market_value_inr)} · {weightInBucket.toFixed(0)}%</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
          <div>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              aria-label={`Remove ${item.bucket} target`}
            >
              Remove
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function AllocationSection() {
  const queryClient = useQueryClient();
  const [activeDim, setActiveDim] = useState<AllocationDimension>('sector');
  const [showForm, setShowForm] = useState(false);
  const [bucket, setBucket] = useState('');
  const [targetPct, setTargetPct] = useState('');
  const [tolerancePct, setTolerancePct] = useState('5');
  const [rationale, setRationale] = useState('');
  // Gates Save when the typed bucket doesn't match anything currently
  // held — re-armed on every bucket/dimension change so it can't be
  // checked once and forgotten for a completely different typo later.
  // Direct response to a real bug: "QSR" (typed) vs the broker's actual
  // "Quick Service Restaurant" silently read as an indistinguishable,
  // verified-looking 0% — this makes that always visible and always an
  // explicit choice, never a silent miss.
  const [confirmUnmatched, setConfirmUnmatched] = useState(false);
  const { error, setError, onError } = useErrorMessage();

  const queries = {
    sector: useQuery({ queryKey: ['allocationProgress', 'sector'], queryFn: () => api.allocationProgress('sector') }),
    asset_class: useQuery({ queryKey: ['allocationProgress', 'asset_class'], queryFn: () => api.allocationProgress('asset_class') }),
    region: useQuery({ queryKey: ['allocationProgress', 'region'], queryFn: () => api.allocationProgress('region') }),
  };
  const activeQuery = queries[activeDim];
  // Same queryKey as Dashboard.tsx's own dashboard fetch — shares its
  // cache instead of a second independent request for the same data.
  const dashboardQuery = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard });
  const holdings = dashboardQuery.data?.holdings ?? [];
  const offTargetCount = (activeQuery.data?.progress ?? []).filter((i) => i.status !== 'on_target').length;

  // Real current allocation for every bucket actually held, regardless of
  // whether a target exists for it yet — only fetched while the form is
  // open, since it's purely a form-assist. Lets the bucket field show
  // "Current: X%" as soon as you type/pick a real bucket, so the target
  // gets set relative to where you actually are (docs/compass-prd.md's
  // whole point for allocation targets) instead of typed blind.
  const breakdownQuery = useQuery({
    queryKey: ['allocationCurrentBreakdown', activeDim],
    queryFn: () => api.allocationCurrentBreakdown(activeDim),
    enabled: showForm,
  });
  // A bucket can be several real names comma-separated (matches the
  // backend's split_bucket_names) — each segment is checked against the
  // real current breakdown independently, same as compute_allocation_progress
  // does server-side, so the hint never says something the saved target
  // wouldn't actually compute.
  const bucketSegments = bucket.split(',').map((s) => s.trim()).filter(Boolean);
  const segmentMatches = bucketSegments.map((seg) => ({
    seg,
    match: breakdownQuery.data?.breakdown.find((b) => b.bucket.toLowerCase() === seg.toLowerCase()),
  }));
  const unmatchedSegments = segmentMatches.filter((s) => !s.match).map((s) => s.seg);
  const matchedSumPct = segmentMatches.reduce((sum, s) => sum + (s.match?.actual_pct ?? 0), 0);
  const currentPctHint = bucketSegments.length === 0 ? null : `${matchedSumPct.toFixed(2)}%`;

  useEffect(() => {
    setConfirmUnmatched(false);
  }, [bucket, activeDim]);

  const createMutation = useMutation({
    mutationFn: () =>
      api.createAllocationTarget({
        dimension: activeDim,
        bucket: bucket.trim(),
        target_pct: Number(targetPct),
        tolerance_pct: Number(tolerancePct) || 5,
        rationale: rationale.trim() || null,
      }),
    onSuccess: () => {
      setError(null);
      setShowForm(false);
      setBucket('');
      setTargetPct('');
      setRationale('');
      setConfirmUnmatched(false);
      queryClient.invalidateQueries({ queryKey: ['allocationProgress', activeDim] });
    },
    onError: (err) => onError(err, 'Failed to create allocation target.'),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!bucket.trim() || !(Number(targetPct) > 0)) {
      setError('Bucket name and a positive target % are required.');
      return;
    }
    if (unmatchedSegments.length > 0 && !confirmUnmatched) {
      setError('Check the box below the bucket field to confirm — this name doesn\'t match anything you currently hold.');
      return;
    }
    createMutation.mutate();
  }

  return (
    <section className="card compass-section">
      <div className="section-head">
        <div className="section-title-row">
          <div>
            <h2 className="section-title">Allocation targets</h2>
            <p className="section-sub">A target composition per dimension — a bucket at 0% against a real target is a named gap</p>
          </div>
          {offTargetCount > 0 && <span className="section-flag">{offTargetCount} off target</span>}
        </div>
        <button className="section-add" onClick={() => setShowForm(true)}>+ Add target</button>
      </div>

      <div className="dim-tabs">
        {DIMENSIONS.map((d) => (
          <button key={d.value} className={`dim-tab${activeDim === d.value ? ' active' : ''}`} onClick={() => setActiveDim(d.value)}>
            {d.label}
          </button>
        ))}
      </div>

      {showForm && (
        <Drawer title="Add allocation target" subtitle="A target composition per dimension" onClose={() => setShowForm(false)}>
          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="field">
              <label>Dimension</label>
              <div className="dim-tabs" style={{ margin: 0 }}>
                {DIMENSIONS.map((d) => (
                  <button type="button" key={d.value} className={`dim-tab${activeDim === d.value ? ' active' : ''}`} onClick={() => setActiveDim(d.value)}>
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <label>Bucket ({DIMENSIONS.find((d) => d.value === activeDim)?.label})</label>
              <input
                type="text"
                list={`bucket-options-${activeDim}`}
                placeholder="Technology"
                value={bucket}
                onChange={(e) => setBucket(e.target.value)}
              />
              <datalist id={`bucket-options-${activeDim}`}>
                {breakdownQuery.data?.breakdown.map((b) => <option key={b.bucket} value={b.bucket} />)}
              </datalist>
              {currentPctHint && <p className="hint">Current: {currentPctHint}</p>}
              {unmatchedSegments.length > 0 && (
                <>
                  <p className="hint" style={{ color: 'var(--loss)' }}>
                    ⚠ {unmatchedSegments.map((s) => `"${s}"`).join(', ')} {unmatchedSegments.length === 1 ? "doesn't" : "don't"} match
                    any current holding — typo, or a real gap you don't hold yet?
                  </p>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                    <input type="checkbox" checked={confirmUnmatched} onChange={(e) => setConfirmUnmatched(e.target.checked)} />
                    I checked — save it anyway
                  </label>
                </>
              )}
            </div>
            <div className="cx-field-row">
              <div className="field">
                <label>Target %</label>
                <input type="number" placeholder="20" value={targetPct} onChange={(e) => setTargetPct(e.target.value)} />
              </div>
              <div className="field">
                <label>Tolerance %</label>
                <input type="number" placeholder="5" value={tolerancePct} onChange={(e) => setTolerancePct(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label>Rationale (optional)</label>
              <textarea
                placeholder="Why this target? e.g. avoid repeating last year's IT-sector concentration."
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={3}
              />
            </div>
            {error && <p className="error-state" style={{ padding: 0 }}>{error}</p>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Saving…' : 'Save target'}
              </button>
            </div>
          </form>
        </Drawer>
      )}

      {activeQuery.isLoading && <p className="loading-state">Loading…</p>}
      {activeQuery.isError && <p className="error-state">Can't reach bridge-server.</p>}
      {activeQuery.data?.progress.length === 0 && <p className="footnote">No {DIMENSIONS.find((d) => d.value === activeDim)?.label.toLowerCase()} targets set yet.</p>}
      {(activeQuery.data?.progress.length ?? 0) > 0 && (
        <div className="alloc-chart">
          {activeQuery.data?.progress.map((item) => (
            <AllocationBucketRow key={item.id} item={item} dimension={activeDim} holdings={holdings} />
          ))}
        </div>
      )}

      {(activeQuery.data?.progress.length ?? 0) > 0 && (
        <div className="dim-legend">
          <span className="dim-legend-item"><span className="dim-legend-swatch" style={{ background: 'var(--accent-soft)', border: '1px solid var(--accent)' }} />target zone (± tolerance)</span>
          <span className="dim-legend-item"><span className="dim-legend-swatch" style={{ background: 'var(--gain)' }} />on target</span>
          <span className="dim-legend-item"><span className="dim-legend-swatch" style={{ background: 'var(--warn)' }} />underweight/overweight</span>
          <span className="dim-legend-item"><span className="dim-legend-swatch" style={{ background: 'var(--loss)' }} />far off / absent</span>
        </div>
      )}
    </section>
  );
}

// ============================================================
// Goals (price_return_pct, dividend_coverage, dividend_amount)
// ============================================================

function GoalRow({ g }: { g: GoalProgressOut }) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteGoal(g.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['goalsProgress'] }),
  });

  const tone = g.status === 'met' ? 'gain' : g.status === 'missed' ? 'loss' : 'neutral';
  const badgeText = { met: 'Met', missed: 'Missed', not_enough_data: 'Not enough data' }[g.status];
  const scopeLabel =
    g.scope_type === 'portfolio' ? 'Portfolio' : g.scope_type === 'sector' ? `Sector — ${g.scope_value}` : g.scope_value?.split(':')[1] ?? g.scope_value;
  const periodLabel =
    g.period === 'trailing_n_days' || g.period === 'trailing_n_months'
      ? 'rolling window'
      : g.period.charAt(0).toUpperCase() + g.period.slice(1);
  const targetLabel =
    g.metric_type === 'dividend_amount'
      ? fmtINR(g.target_value)
      : g.metric_type === 'price_return_pct'
        ? `${g.target_value}%`
        : `${g.target_value} months`;

  const progressPct = g.metric_type === 'dividend_coverage' && g.window_months ? Math.min(100, (g.actual_value ?? 0) / g.window_months * 100) : null;

  return (
    <div className={`item-row${expanded ? ' expanded' : ''}`} onClick={() => setExpanded((v) => !v)} role="button" tabIndex={0}>
      <div>
        <p className="item-name">{g.name}</p>
        <p className="item-meta">
          {scopeLabel} · {periodLabel} · target {g.comparison === 'gte' ? '≥' : '≤'} {targetLabel}
        </p>
      </div>
      <div>{progressPct != null && <div className="mini-track"><div className="mini-fill" style={{ width: `${progressPct}%`, background: g.status === 'met' ? 'var(--gain)' : 'var(--warn)' }} /></div>}</div>
      <div className="item-figs">
        {g.actual_value == null ? (
          <span className="item-of">no data yet</span>
        ) : g.metric_type === 'price_return_pct' ? (
          <>
            <span className={`item-cur mono ${g.actual_value >= 0 ? 'tone-gain' : 'tone-loss'}`}>{fmtPct(g.actual_value)}</span>
            <span className="item-of">vs target {fmtPct(g.target_value)}</span>
          </>
        ) : g.metric_type === 'dividend_coverage' ? (
          <>
            <span className="item-cur mono">{g.actual_value} <span style={{ fontSize: 11, fontWeight: 400 }}>of {g.window_months}</span></span>
            <span className="item-of">months covered</span>
          </>
        ) : (
          <>
            <span className={`item-cur mono ${g.status === 'met' ? 'tone-gain' : 'tone-loss'}`}>{fmtINR(g.actual_value)}</span>
            <span className="item-of">of {fmtINR(g.target_value)}</span>
          </>
        )}
      </div>
      <StatusBadge tone={tone}>{badgeText}</StatusBadge>
      <span className="item-chev">{expanded ? '▾' : '▸'}</span>

      {expanded && (
        <div className="item-detail" onClick={(e) => e.stopPropagation()}>
          {g.actual_value == null ? (
            <p className="item-rationale">Not enough data yet to compute this goal.</p>
          ) : g.metric_type === 'price_return_pct' ? (
            <>
              {g.period_start && (
                <p className="item-of" style={{ margin: 0 }}>since {g.period_start}</p>
              )}
              {g.contributions && g.contributions.length > 0 && (
                <div>
                  <p className="detail-stat-label">What happened ({g.contributions.length} holdings)</p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                    {g.contributions.map((c) => (
                      <div className="contrib-row" key={`${c.broker}:${c.symbol}`}>
                        <span className="contrib-sym">{c.symbol}</span>
                        <div className="contrib-track">
                          <div className="contrib-mid" />
                          <div
                            className={`contrib-fill ${c.contribution_pp >= 0 ? 'tone-gain' : 'tone-loss'}`}
                            style={{ width: `${Math.min(50, Math.abs(c.contribution_pp) * 4)}%` }}
                          />
                        </div>
                        <span className={`contrib-val mono ${c.contribution_pp >= 0 ? 'tone-gain' : 'tone-loss'}`}>
                          {c.contribution_pp >= 0 ? '+' : ''}{c.contribution_pp}pp
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : g.metric_type === 'dividend_coverage' ? (
            <>
              {g.coverage && (
                <div className="coverage-row">
                  {g.coverage.map((c) => (
                    <div className="coverage-chip" key={`${c.year}-${c.month}`}>
                      <div className={`coverage-dot ${c.covered ? 'filled' : 'empty'}`}>{c.covered ? '✓' : '—'}</div>
                      <span className="coverage-month">{MONTH_NAMES[c.month - 1]}</span>
                    </div>
                  ))}
                </div>
              )}
              {g.gap_months && g.gap_months.length > 0 && (
                <p className="item-of" style={{ margin: 0 }}>Gap months: {g.gap_months.join(', ')} — no dividend logged.</p>
              )}
            </>
          ) : (
            g.prior_period_total_inr != null && <p className="item-of" style={{ margin: 0 }}>Prior period: {fmtINR(g.prior_period_total_inr)}.</p>
          )}
          {g.rationale && <p className="item-rationale">{g.rationale}</p>}
          <div>
            <button className="btn btn-ghost btn-sm" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
              Remove
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const METRIC_TYPES: { value: GoalMetricType; label: string }[] = [
  { value: 'price_return_pct', label: 'Price return %' },
  { value: 'dividend_coverage', label: 'Dividend coverage' },
  { value: 'dividend_amount', label: 'Dividend amount' },
];

function GoalsSection() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [metricType, setMetricType] = useState<GoalMetricType>('price_return_pct');
  const [scopeType, setScopeType] = useState<GoalScopeType>('portfolio');
  const [scopeValue, setScopeValue] = useState('');
  const [targetValue, setTargetValue] = useState('');
  const [period, setPeriod] = useState('monthly');
  const [periodN, setPeriodN] = useState('6');
  const [rationale, setRationale] = useState('');
  const { error, setError, onError } = useErrorMessage();

  const progressQuery = useQuery({ queryKey: ['goalsProgress'], queryFn: api.goalsProgress });
  const goals = progressQuery.data ?? [];
  const missedCount = goals.filter((g) => g.status === 'missed').length;

  const createMutation = useMutation({
    mutationFn: () =>
      api.createGoal({
        name,
        metric_type: metricType,
        target_value: Number(targetValue),
        scope_type: metricType === 'price_return_pct' ? scopeType : 'portfolio',
        scope_value: metricType === 'price_return_pct' && scopeType !== 'portfolio' ? scopeValue.trim() : null,
        period: metricType === 'dividend_coverage' ? 'trailing_n_months' : period,
        period_n:
          metricType === 'dividend_coverage'
            ? Number(periodN) || 6
            : period === 'trailing_n_days'
              ? Number(periodN) || 30
              : null,
        rationale: rationale.trim() || null,
      }),
    onSuccess: () => {
      setError(null);
      setShowForm(false);
      setName('');
      setTargetValue('');
      setScopeValue('');
      setRationale('');
      queryClient.invalidateQueries({ queryKey: ['goalsProgress'] });
    },
    onError: (err) => onError(err, 'Failed to create goal.'),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !(Number(targetValue) > 0)) {
      setError('Name and a positive target value are required.');
      return;
    }
    if (metricType === 'price_return_pct' && scopeType !== 'portfolio' && !scopeValue.trim()) {
      setError(scopeType === 'sector' ? 'Enter the sector name.' : 'Enter as "broker:symbol", e.g. paytmmoney:SWIGGY.');
      return;
    }
    createMutation.mutate();
  }

  return (
    <section className="card compass-section">
      <div className="section-head">
        <div className="section-title-row">
          <div>
            <h2 className="section-title">Goals</h2>
            <p className="section-sub">A single number checked against a target, over a period</p>
          </div>
          {missedCount > 0 && <span className="section-flag">{missedCount} missed</span>}
        </div>
        <button className="section-add" onClick={() => setShowForm(true)}>+ Add goal</button>
      </div>

      {showForm && (
        <Drawer title="Add goal" subtitle="A single number checked against a target, over a period" onClose={() => setShowForm(false)}>
          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="field">
              <label>Name</label>
              <input type="text" placeholder="Portfolio return this month" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label>Metric</label>
              <select value={metricType} onChange={(e) => setMetricType(e.target.value as GoalMetricType)}>
                {METRIC_TYPES.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Target {metricType === 'price_return_pct' ? '(%)' : metricType === 'dividend_amount' ? '(₹)' : '(months covered)'}</label>
              <input type="number" value={targetValue} onChange={(e) => setTargetValue(e.target.value)} />
              {metricType === 'dividend_amount' && Number(targetValue) > 0 && <p className="hint">= {fmtINR(Number(targetValue))}</p>}
            </div>

            {/* Only the fields that actually apply to the current metric
                are rendered — a metric switch shouldn't leave dead space
                behind for fields it doesn't use. */}
            {metricType === 'price_return_pct' && (
              <div className="cx-field-row">
                <div className="field">
                  <label>Scope</label>
                  <select value={scopeType} onChange={(e) => setScopeType(e.target.value as GoalScopeType)}>
                    <option value="portfolio">Portfolio</option>
                    <option value="sector">Sector</option>
                    <option value="holding">Holding</option>
                  </select>
                </div>
                {scopeType !== 'portfolio' && (
                  <div className="field">
                    <label>{scopeType === 'sector' ? 'Sector name' : 'broker:symbol'}</label>
                    <input
                      type="text"
                      placeholder={scopeType === 'sector' ? 'Technology' : 'paytmmoney:SWIGGY'}
                      value={scopeValue}
                      onChange={(e) => setScopeValue(e.target.value)}
                    />
                  </div>
                )}
              </div>
            )}
            <div className="cx-field-row">
              {metricType === 'dividend_coverage' ? (
                <div className="field">
                  <label>Trailing window (months)</label>
                  <input type="number" value={periodN} onChange={(e) => setPeriodN(e.target.value)} />
                </div>
              ) : (
                <>
                  <div className="field">
                    <label>Period</label>
                    <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      {metricType === 'price_return_pct' && <option value="yearly">Yearly</option>}
                      <option value="trailing_n_days">Trailing (days) — not calendar-anchored</option>
                    </select>
                  </div>
                  {period === 'trailing_n_days' && (
                    <div className="field">
                      <label>Trailing window (days)</label>
                      <input type="number" placeholder="90" value={periodN} onChange={(e) => setPeriodN(e.target.value)} />
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="field">
              <label>Rationale (optional)</label>
              <textarea
                placeholder="Why this goal? e.g. want to beat what a fixed deposit would've paid this quarter."
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={3}
              />
            </div>
            {error && <p className="error-state" style={{ padding: 0 }}>{error}</p>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Saving…' : 'Save goal'}
              </button>
            </div>
          </form>
        </Drawer>
      )}

      <div className="row-list">
        {progressQuery.isLoading && <p className="loading-state">Loading…</p>}
        {progressQuery.isError && <p className="error-state">Can't reach bridge-server.</p>}
        {goals.length === 0 && !progressQuery.isLoading && <p className="footnote" style={{ margin: '0 20px 4px' }}>No goals set yet.</p>}
        {goals.map((g) => <GoalRow key={g.id} g={g} />)}
      </div>
    </section>
  );
}

// ============================================================
// Dividend log
// ============================================================

function DividendRow({ d }: { d: DividendOut }) {
  const queryClient = useQueryClient();
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteDividend(d.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dividends'] });
      queryClient.invalidateQueries({ queryKey: ['goalsProgress'] });
    },
  });
  return (
    <tr>
      <td><span className="sym">{d.symbol}</span><div className="sub">{d.broker}</div></td>
      <td className="num">{fmtINR(d.amount_inr)}</td>
      <td>{d.payment_date}</td>
      <td>{d.notes ?? ''}</td>
      <td style={{ textAlign: 'right' }}>
        <button className="btn btn-ghost btn-sm" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
          Remove
        </button>
      </td>
    </tr>
  );
}

function DividendsSection() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [broker, setBroker] = useState('paytmmoney');
  const [symbol, setSymbol] = useState('');
  const [amount, setAmount] = useState('');
  const [paymentDate, setPaymentDate] = useState('');
  const { error, setError, onError } = useErrorMessage();

  const dividendsQuery = useQuery({ queryKey: ['dividends'], queryFn: api.dividends });

  const createMutation = useMutation({
    mutationFn: () => api.createDividend({ broker, symbol: symbol.trim(), amount_inr: Number(amount), payment_date: paymentDate }),
    onSuccess: () => {
      setError(null);
      setShowForm(false);
      setSymbol('');
      setAmount('');
      setPaymentDate('');
      queryClient.invalidateQueries({ queryKey: ['dividends'] });
      queryClient.invalidateQueries({ queryKey: ['goalsProgress'] });
    },
    onError: (err) => onError(err, 'Failed to log dividend.'),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!symbol.trim() || !(Number(amount) > 0) || !paymentDate) {
      setError('Symbol, a positive amount, and a payment date are required.');
      return;
    }
    createMutation.mutate();
  }

  return (
    <section className="card compass-section">
      <div className="section-head">
        <div className="section-title-row">
          <div>
            <h2 className="section-title">Dividend log</h2>
            <p className="section-sub">Logged by hand — no broker exposes this data programmatically (see docs/compass-prd.md §8)</p>
          </div>
        </div>
        <button className="section-add" onClick={() => setShowForm(true)}>+ Log dividend</button>
      </div>

      {showForm && (
        <Drawer title="Log dividend" subtitle="Logged by hand — no broker exposes this data programmatically" onClose={() => setShowForm(false)}>
          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="field">
              <label>Broker</label>
              <select value={broker} onChange={(e) => setBroker(e.target.value)}>
                <option value="paytmmoney">PaytmMoney</option>
                <option value="indmoney">INDmoney</option>
              </select>
            </div>
            <div className="field">
              <label>Symbol</label>
              <input type="text" placeholder="ITC" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
            </div>
            <div className="cx-field-row">
              <div className="field">
                <label>Amount (₹)</label>
                <input type="number" placeholder="250" value={amount} onChange={(e) => setAmount(e.target.value)} />
                {Number(amount) > 0 && <p className="hint">= {fmtINR(Number(amount))}</p>}
              </div>
              <div className="field">
                <label>Payment date</label>
                <input type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} />
              </div>
            </div>
            {error && <p className="error-state" style={{ padding: 0 }}>{error}</p>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </Drawer>
      )}

      {dividendsQuery.isLoading && <p className="loading-state">Loading…</p>}
      {dividendsQuery.isError && <p className="error-state">Can't reach bridge-server.</p>}
      {dividendsQuery.data?.dividends.length === 0 && <p className="footnote">No dividends logged yet.</p>}
      {(dividendsQuery.data?.dividends.length ?? 0) > 0 && (
        <div className="table-wrap">
          <table className="data-table table-vlines">
            <thead>
              <tr>
                <th>Holding</th>
                <th className="num">Amount</th>
                <th>Date</th>
                <th>Notes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>{dividendsQuery.data?.dividends.map((d) => <DividendRow key={d.id} d={d} />)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ============================================================
// Page
// ============================================================

export function Compass() {
  return (
    <>
      <div className="topbar">
        <div>
          <h1 className="topbar-title">Compass</h1>
          <p className="topbar-sub">Where you said you wanted to go, and how close you actually are — with real diagnosis when you're not.</p>
        </div>
      </div>

      <div style={{ marginTop: 20 }}>
        <OverviewStrip />
        <MilestonesSection />
        <AllocationSection />
        <GoalsSection />
        <DividendsSection />
        <RiskControlsSection />
      </div>
    </>
  );
}
