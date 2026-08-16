// Compass (docs/compass-prd.md) — goal-setting and diagnosis for the
// portfolio. Three shapes assembled into one page: Milestone (deadline),
// AllocationTarget (composition), Goal (scalar, incl. dividend metric
// types) — plus the raw Dividend log those last two read from, and Risk
// Controls (RiskControlsSection, moved in from the old standalone
// /thresholds page) — guardrails rather than targets, kept as their own
// section rather than reshaped into one of the three target shapes.
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';
import { RiskControlsSection } from '../components/RiskControlsSection';
import type {
  AllocationDimension,
  AllocationProgressItem,
  DividendOut,
  GoalMetricType,
  GoalProgressOut,
  GoalScopeType,
  MilestoneMetricType,
  MilestoneProgressOut,
} from '../api/types';
import { fmtINR, fmtPct, fmtSigned } from '../lib/format';

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

function useErrorMessage() {
  const [error, setError] = useState<string | null>(null);
  return {
    error,
    setError,
    onError: (err: unknown, fallback: string) => setError(err instanceof ApiError ? err.message : fallback),
  };
}

// ============================================================
// Milestones
// ============================================================

function MilestoneCard({ m }: { m: MilestoneProgressOut }) {
  const queryClient = useQueryClient();
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteMilestone(m.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['milestonesProgress'] }),
  });

  const progressPct = m.progress_pct != null ? Math.min(100, Math.max(0, m.progress_pct)) : null;
  const badgeClass = m.status === 'met' || m.status === 'on_pace' ? 'badge-gain' : m.status === 'behind' ? 'badge-loss' : 'badge-neutral';
  const badgeText = { met: 'Met', on_pace: 'On pace', behind: 'Behind', not_enough_data: 'Not enough data' }[m.status];
  // progress_pct is null for pnl_pct by design (app/milestones.py's
  // _progress_pct docstring) — a percent-of-target ratio doesn't
  // generalize past net_worth, so there's no bar to fill for that type,
  // just the current/target figures themselves.
  const fmtValue = m.metric_type === 'pnl_pct' ? fmtPct : fmtINR;

  return (
    <div className="card milestone-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p className="milestone-name">{m.name}</p>
          <p className="milestone-target">
            Target date: {m.target_date}
            {m.days_remaining != null && ` · ${m.days_remaining >= 0 ? `${m.days_remaining} days away` : `${-m.days_remaining} days overdue`}`}
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
          Remove
        </button>
      </div>
      {m.current_value != null ? (
        <>
          <div className="milestone-figures">
            <span className="milestone-current mono">{fmtValue(m.current_value)}</span>
            <span className="milestone-of mono">
              of {fmtValue(m.target_value)}
              {progressPct != null && ` · ${m.progress_pct}%`}
            </span>
          </div>
          {progressPct != null && (
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${progressPct}%` }} />
            </div>
          )}
          <div className="milestone-pace">
            <span className={`badge ${badgeClass}`}>
              <span className="badge-dot" />
              {badgeText}
            </span>
            {m.status === 'met' && <span>Target reached.</span>}
            {m.status === 'on_pace' && m.projected_date && (
              <span>At your recent rate, you'd reach this around <strong>{m.projected_date}</strong>.</span>
            )}
            {m.status === 'behind' && m.projected_date && (
              <span>
                At your recent rate, you'd reach this around <strong>{m.projected_date}</strong> — after the target date.
              </span>
            )}
            {m.status === 'behind' && !m.projected_date && <span>Current trend doesn't reach this target.</span>}
          </div>

          <details className="why-toggle">
            <summary>▸ Why</summary>
            <div className="why-body">
              {m.status === 'met' ? (
                <p>
                  Already past the target — {fmtValue(m.current_value)} vs a target of {fmtValue(m.target_value)} by {m.target_date}.
                </p>
              ) : m.actual_pace_per_day != null ? (
                <>
                  <p>
                    Recent pace: <strong className="mono">{fmtPace(m.actual_pace_per_day, m.metric_type)}/day</strong> over the last{' '}
                    {m.pace_window_days} days.
                  </p>
                  <p>
                    Reaching {fmtValue(m.target_value)} by {m.target_date} needs{' '}
                    {m.required_pace_per_day != null ? (
                      <strong className="mono">{fmtPace(m.required_pace_per_day, m.metric_type)}/day</strong>
                    ) : (
                      'an unknown pace'
                    )}
                    .
                  </p>
                  {m.actual_pace_per_day <= 0 && (
                    <p>Recent trend is flat or shrinking, so it never reaches the target on its own — it would need to turn around first.</p>
                  )}
                </>
              ) : (
                <p>
                  Not enough portfolio history in the last {m.pace_window_days} days yet to compute a real trend.
                  {m.required_pace_per_day != null && (
                    <>
                      {' '}
                      Hitting {fmtValue(m.target_value)} by {m.target_date} needs an average of{' '}
                      <strong className="mono">{fmtPace(m.required_pace_per_day, m.metric_type)}/day</strong> from here.
                    </>
                  )}
                </p>
              )}
            </div>
          </details>
        </>
      ) : (
        <p className="loading-state" style={{ padding: '8px 0' }}>
          Not enough portfolio history yet to compute progress.
        </p>
      )}
      {m.rationale && (
        <details className="why-toggle">
          <summary>▸ Rationale</summary>
          <div className="why-body">
            <p>{m.rationale}</p>
          </div>
        </details>
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
        <div>
          <h2 className="section-title">Milestone</h2>
          <p className="section-sub">A target reached by a date, not a recurring check</p>
        </div>
        <button className="section-add" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add milestone'}
        </button>
      </div>

      {showForm && (
        <form className="compass-form" onSubmit={submit}>
          <div className="form-row" style={{ gridTemplateColumns: '1.2fr 1fr 1fr 1fr auto' }}>
            <div className="field">
              <label>Name</label>
              <input
                type="text"
                placeholder={metricType === 'pnl_pct' ? 'Break even' : 'Reach ₹50,00,000 net worth'}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="field">
              <label>Metric</label>
              <select value={metricType} onChange={(e) => setMetricType(e.target.value as MilestoneMetricType)}>
                {MILESTONE_METRIC_TYPES.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>{metricType === 'pnl_pct' ? 'Target P&L (%)' : 'Target (₹)'}</label>
              <input
                type="number"
                step={metricType === 'pnl_pct' ? '0.1' : '1'}
                placeholder={metricType === 'pnl_pct' ? '0' : '5000000'}
                value={targetValue}
                onChange={(e) => setTargetValue(e.target.value)}
              />
            </div>
            <div className="field">
              <label>Target date</label>
              <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
            </div>
            <div className="field">
              <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
          <div className="form-row" style={{ gridTemplateColumns: '1fr' }}>
            <div className="field">
              <label>Rationale (optional)</label>
              <textarea
                placeholder="Why this milestone? e.g. tuition due in mid-2027, want a real cushion above it."
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={2}
              />
            </div>
          </div>
        </form>
      )}
      {error && <p className="error-state" style={{ padding: '0 0 12px' }}>{error}</p>}

      {progressQuery.isLoading && <p className="loading-state">Loading…</p>}
      {progressQuery.isError && <p className="error-state">Can't reach bridge-server.</p>}
      {progressQuery.data?.length === 0 && <p className="footnote">No milestones set yet.</p>}
      {progressQuery.data?.map((m) => <MilestoneCard key={m.id} m={m} />)}
    </section>
  );
}

// ============================================================
// Allocation targets
// ============================================================

function BucketRow({ item }: { item: AllocationProgressItem }) {
  const queryClient = useQueryClient();
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteAllocationTarget(item.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['allocationProgress'] }),
  });

  const zoneLeft = Math.max(0, item.target_pct - item.tolerance_pct);
  const zoneWidth = item.tolerance_pct * 2;
  const actualClamped = Math.min(100, Math.max(0, item.actual_pct));
  const tone = item.status === 'on_target' ? 'tone-gain' : item.actual_pct < item.target_pct - item.tolerance_pct * 2 ? 'tone-loss' : 'tone-warn';

  return (
    <>
      <div className="bucket-row">
        <span className="bucket-name">{item.bucket}</span>
        <div className="bucket-track">
          <div className="rail-bg" />
          <div className="bucket-target-zone" style={{ left: `${zoneLeft}%`, width: `${zoneWidth}%` }} />
          <div className={`bucket-actual-fill ${tone}`} style={{ width: `${actualClamped}%` }} />
          <div className="bucket-marker" style={{ left: `${actualClamped}%` }} />
        </div>
        <div className="bucket-figures">
          <span className="bucket-actual-val mono">{item.actual_pct}%</span>
          <span className="bucket-target-val mono">target {item.target_pct}%</span>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
          ×
        </button>
      </div>
      {item.unmatched_bucket_names.length > 0 ? (
        // Real bug found via a user's own manual reconciliation against
        // the Dashboard: a typo'd bucket name (e.g. "QSR" vs the broker's
        // real "Quick Service Restaurant") used to silently read as an
        // indistinguishable, verified-looking 0% gap. This is the fix —
        // a distinct, unmissable warning whenever the name doesn't match
        // anything currently held, instead of a number that looks real
        // but might not be.
        <p className="bucket-gap-note tone-loss">
          ⚠ {item.unmatched_bucket_names.map((n) => `"${n}"`).join(', ')} — {item.unmatched_bucket_names.length === 1 ? "doesn't" : "don't"} match any
          of your current holdings' real {item.dimension} names. This number may be wrong, not a verified gap — check the
          exact spelling on the Dashboard's breakdown (or this may genuinely be something you don't hold yet).
        </p>
      ) : (
        item.status !== 'on_target' && (
          <p className={`bucket-gap-note ${tone === 'tone-loss' ? 'tone-loss' : 'tone-warn'}`}>
            {item.actual_pct === 0
              ? `No holding in this bucket at all — ${Math.abs(item.gap_pct).toFixed(1)}pp under target.`
              : `${item.status === 'underweight' ? `${Math.abs(item.gap_pct).toFixed(1)}pp under` : `${Math.abs(item.gap_pct).toFixed(1)}pp over`} target.`}
          </p>
        )
      )}
      {item.rationale && (
        <details className="why-toggle">
          <summary>▸ Rationale</summary>
          <div className="why-body">
            <p>{item.rationale}</p>
          </div>
        </details>
      )}
    </>
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
        <div>
          <h2 className="section-title">Allocation targets</h2>
          <p className="section-sub">A target composition per dimension — a bucket at 0% against a real target is a named gap</p>
        </div>
        <button className="section-add" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add target'}
        </button>
      </div>

      <div className="dim-tabs">
        {DIMENSIONS.map((d) => (
          <button key={d.value} className={`dim-tab${activeDim === d.value ? ' active' : ''}`} onClick={() => setActiveDim(d.value)}>
            {d.label}
          </button>
        ))}
      </div>

      {showForm && (
        <form className="compass-form" onSubmit={submit}>
          <div className="form-row" style={{ gridTemplateColumns: '1.2fr 0.8fr 0.8fr auto' }}>
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
            <div className="field">
              <label>Target %</label>
              <input type="number" placeholder="20" value={targetPct} onChange={(e) => setTargetPct(e.target.value)} />
            </div>
            <div className="field">
              <label>Tolerance %</label>
              <input type="number" placeholder="5" value={tolerancePct} onChange={(e) => setTolerancePct(e.target.value)} />
            </div>
            <div className="field">
              <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
          <div className="form-row" style={{ gridTemplateColumns: '1fr' }}>
            <div className="field">
              <label>Rationale (optional)</label>
              <textarea
                placeholder="Why this target? e.g. avoid repeating last year's IT-sector concentration."
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={2}
              />
            </div>
          </div>
        </form>
      )}
      {error && <p className="error-state" style={{ padding: '0 0 12px' }}>{error}</p>}

      {activeQuery.isLoading && <p className="loading-state">Loading…</p>}
      {activeQuery.isError && <p className="error-state">Can't reach bridge-server.</p>}
      {activeQuery.data?.progress.length === 0 && <p className="footnote">No {DIMENSIONS.find((d) => d.value === activeDim)?.label.toLowerCase()} targets set yet.</p>}
      {activeQuery.data?.progress.map((item) => <BucketRow key={item.id} item={item} />)}

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

function GoalCard({ g }: { g: GoalProgressOut }) {
  const queryClient = useQueryClient();
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteGoal(g.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['goalsProgress'] }),
  });

  const badgeClass = g.status === 'met' ? 'badge-gain' : g.status === 'missed' ? 'badge-loss' : 'badge-neutral';
  const badgeText = { met: 'Met', missed: 'Missed', not_enough_data: 'Not enough data' }[g.status];
  const scopeLabel =
    g.scope_type === 'portfolio' ? 'Portfolio' : g.scope_type === 'sector' ? `Sector — ${g.scope_value}` : g.scope_value?.split(':')[1] ?? g.scope_value;
  // trailing_n_days is a rolling window, not a calendar-anchored period —
  // "TRAILING_N_DAYS" read as a raw enum value; the exact window shows up
  // anyway via "since {period_start}" in the readout below, so the meta
  // line just needs to say what kind of window this is, not repeat the date.
  const periodLabel = g.period === 'trailing_n_days' ? 'ROLLING WINDOW' : g.period.toUpperCase();

  return (
    <div className="card goal-card">
      <div className="goal-top">
        <div>
          <p className="goal-name">{g.name}</p>
          <p className="goal-meta">
            SCOPE: {scopeLabel?.toUpperCase()} · PERIOD: {periodLabel} · TARGET:{' '}
            {g.comparison === 'gte' ? '≥' : '≤'} {g.target_value}
            {g.metric_type === 'price_return_pct' ? '%' : g.metric_type === 'dividend_amount' ? '' : ' months'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className={`badge ${badgeClass}`}>
            <span className="badge-dot" />
            {badgeText}
          </span>
          <button className="btn btn-ghost btn-sm" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
            Remove
          </button>
        </div>
      </div>

      {g.actual_value == null ? (
        <p className="loading-state" style={{ padding: '8px 0' }}>Not enough data yet to compute this goal.</p>
      ) : g.metric_type === 'price_return_pct' ? (
        <>
          <div className="goal-readout">
            <span className={`goal-actual mono ${g.actual_value >= 0 ? 'tone-gain' : 'tone-loss'}`}>{fmtPct(g.actual_value)}</span>
            <span className="goal-target-note">vs. target {fmtPct(g.target_value)}, {g.period_start && `since ${g.period_start}`}</span>
          </div>
          {g.contributions && g.contributions.length > 0 && (
            <details className="why-toggle">
              <summary>▸ What happened ({g.contributions.length} holdings)</summary>
              <div className="why-body">
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
                      {c.contribution_pp >= 0 ? '+' : ''}
                      {c.contribution_pp}pp
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </>
      ) : g.metric_type === 'dividend_coverage' ? (
        <>
          <div className="goal-readout">
            <span className={`goal-actual mono ${g.status === 'met' ? 'tone-gain' : 'tone-loss'}`}>
              {g.actual_value} of {g.window_months}
            </span>
            <span className="goal-target-note">months covered, target ≥ {g.target_value}</span>
          </div>
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
            <p className="footnote">Gap months: {g.gap_months.join(', ')} — no dividend logged.</p>
          )}
        </>
      ) : (
        <>
          <div className="goal-readout">
            <span className={`goal-actual mono ${g.status === 'met' ? 'tone-gain' : 'tone-loss'}`}>{fmtINR(g.actual_value)}</span>
            <span className="goal-target-note">of {fmtINR(g.target_value)} target</span>
          </div>
          {g.prior_period_total_inr != null && (
            <p className="footnote">Prior period: {fmtINR(g.prior_period_total_inr)}.</p>
          )}
        </>
      )}
      {g.rationale && (
        <details className="why-toggle">
          <summary>▸ Rationale</summary>
          <div className="why-body">
            <p>{g.rationale}</p>
          </div>
        </details>
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
        <div>
          <h2 className="section-title">Goals</h2>
          <p className="section-sub">A single number checked against a target, over a period</p>
        </div>
        <button className="section-add" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add goal'}
        </button>
      </div>

      {showForm && (
        <form className="compass-form" onSubmit={submit}>
          <div className="form-row" style={{ gridTemplateColumns: '1.3fr 1fr 1fr' }}>
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
            </div>
          </div>

          {/* Always the same 4-slot row, regardless of metric — previously
              3 slots, but "trailing (days)" needed its own dedicated N
              field alongside the period selector rather than overloading
              the scope-value slot (a rolling window applies to
              price_return_pct/dividend_amount regardless of scope).
              Slots 1-2 are price_return_pct-only scope extras; slot 3 is
              the trailing-N count (months for dividend_coverage, days for
              a rolling window on the other two); slot 4 is the period
              selector. Unused slots render as invisible spacers so the
              row never changes shape when the metric changes. */}
          <div className="form-row" style={{ gridTemplateColumns: '0.8fr 1fr 0.8fr 1fr' }}>
            {metricType === 'price_return_pct' ? (
              <div className="field">
                <label>Scope</label>
                <select value={scopeType} onChange={(e) => setScopeType(e.target.value as GoalScopeType)}>
                  <option value="portfolio">Portfolio</option>
                  <option value="sector">Sector</option>
                  <option value="holding">Holding</option>
                </select>
              </div>
            ) : (
              <div className="field" aria-hidden="true" />
            )}
            {metricType === 'price_return_pct' && scopeType !== 'portfolio' ? (
              <div className="field">
                <label>{scopeType === 'sector' ? 'Sector name' : 'broker:symbol'}</label>
                <input
                  type="text"
                  placeholder={scopeType === 'sector' ? 'Technology' : 'paytmmoney:SWIGGY'}
                  value={scopeValue}
                  onChange={(e) => setScopeValue(e.target.value)}
                />
              </div>
            ) : (
              <div className="field" aria-hidden="true" />
            )}
            {metricType === 'dividend_coverage' ? (
              <div className="field">
                <label>Trailing window (months)</label>
                <input type="number" value={periodN} onChange={(e) => setPeriodN(e.target.value)} />
              </div>
            ) : period === 'trailing_n_days' ? (
              <div className="field">
                <label>Trailing window (days)</label>
                <input type="number" placeholder="90" value={periodN} onChange={(e) => setPeriodN(e.target.value)} />
              </div>
            ) : (
              <div className="field" aria-hidden="true" />
            )}
            {metricType === 'dividend_coverage' ? (
              <div className="field" aria-hidden="true" />
            ) : (
              <div className="field">
                <label>Period</label>
                <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                  <option value="monthly">Monthly</option>
                  <option value="quarterly">Quarterly</option>
                  {metricType === 'price_return_pct' && <option value="yearly">Yearly</option>}
                  <option value="trailing_n_days">Trailing (days) — not calendar-anchored</option>
                </select>
              </div>
            )}
          </div>
          <div className="form-row" style={{ gridTemplateColumns: '1fr' }}>
            <div className="field">
              <label>Rationale (optional)</label>
              <textarea
                placeholder="Why this goal? e.g. want to beat what a fixed deposit would've paid this quarter."
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={2}
              />
            </div>
          </div>
          <div style={{ marginTop: 10 }}>
            <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Saving…' : 'Save goal'}
            </button>
          </div>
        </form>
      )}
      {error && <p className="error-state" style={{ padding: '0 0 12px' }}>{error}</p>}

      {progressQuery.isLoading && <p className="loading-state">Loading…</p>}
      {progressQuery.isError && <p className="error-state">Can't reach bridge-server.</p>}
      {progressQuery.data?.length === 0 && <p className="footnote">No goals set yet.</p>}
      <div className="stack">
        {progressQuery.data?.map((g) => <GoalCard key={g.id} g={g} />)}
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
        <div>
          <h2 className="section-title">Dividend log</h2>
          <p className="section-sub">Logged by hand — no broker exposes this data programmatically (see docs/compass-prd.md §8)</p>
        </div>
        <button className="section-add" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Log dividend'}
        </button>
      </div>

      {showForm && (
        <form className="compass-form" onSubmit={submit}>
          <div className="form-row" style={{ gridTemplateColumns: '0.8fr 1fr 0.8fr 0.9fr auto' }}>
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
            <div className="field">
              <label>Amount (₹)</label>
              <input type="number" placeholder="250" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
            <div className="field">
              <label>Payment date</label>
              <input type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} />
            </div>
            <div className="field">
              <button className="btn btn-primary" type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </form>
      )}
      {error && <p className="error-state" style={{ padding: '0 0 12px' }}>{error}</p>}

      {dividendsQuery.isLoading && <p className="loading-state">Loading…</p>}
      {dividendsQuery.isError && <p className="error-state">Can't reach bridge-server.</p>}
      {dividendsQuery.data?.dividends.length === 0 && <p className="footnote">No dividends logged yet.</p>}
      {(dividendsQuery.data?.dividends.length ?? 0) > 0 && (
        <div className="table-wrap">
          <table className="data-table">
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
// Summary strip
// ============================================================

function SummaryStrip() {
  const goalsProgress = useQuery({ queryKey: ['goalsProgress'], queryFn: api.goalsProgress });
  const milestonesProgress = useQuery({ queryKey: ['milestonesProgress'], queryFn: api.milestonesProgress });
  const sectorProgress = useQuery({ queryKey: ['allocationProgress', 'sector'], queryFn: () => api.allocationProgress('sector') });
  const assetClassProgress = useQuery({ queryKey: ['allocationProgress', 'asset_class'], queryFn: () => api.allocationProgress('asset_class') });
  const regionProgress = useQuery({ queryKey: ['allocationProgress', 'region'], queryFn: () => api.allocationProgress('region') });

  const goals = goalsProgress.data ?? [];
  const goalsMet = goals.filter((g) => g.status === 'met').length;

  const allocationItems = [...(sectorProgress.data?.progress ?? []), ...(assetClassProgress.data?.progress ?? []), ...(regionProgress.data?.progress ?? [])];
  const onTarget = allocationItems.filter((i) => i.status === 'on_target').length;

  const milestones = milestonesProgress.data ?? [];
  const onPace = milestones.filter((m) => m.status === 'met' || m.status === 'on_pace').length;

  return (
    <div className="summary-strip">
      <div className={`summary-tile ${goals.length > 0 && goalsMet === goals.length ? 'tone-gain' : goals.length > 0 ? 'tone-warn' : ''}`}>
        <p className="summary-tile-label">Goals on track</p>
        <p className="summary-tile-figure mono">{goalsMet}<span className="of">of {goals.length}</span></p>
      </div>
      <div className={`summary-tile ${allocationItems.length > 0 && onTarget === allocationItems.length ? 'tone-gain' : allocationItems.length > 0 ? 'tone-warn' : ''}`}>
        <p className="summary-tile-label">Allocation targets</p>
        <p className="summary-tile-figure mono">{onTarget}<span className="of">of {allocationItems.length} on target</span></p>
      </div>
      <div className={`summary-tile ${milestones.length > 0 && onPace === milestones.length ? 'tone-gain' : milestones.length > 0 ? 'tone-warn' : ''}`}>
        <p className="summary-tile-label">Milestones</p>
        <p className="summary-tile-figure mono">{onPace}<span className="of">of {milestones.length} on pace</span></p>
      </div>
      <div className="summary-tile">
        <p className="summary-tile-label">Dividend log</p>
        <p className="summary-tile-figure mono" style={{ fontSize: 16 }}>See below</p>
      </div>
    </div>
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
        <SummaryStrip />
        <MilestonesSection />
        <AllocationSection />
        <GoalsSection />
        <DividendsSection />
        <RiskControlsSection />
      </div>
    </>
  );
}
