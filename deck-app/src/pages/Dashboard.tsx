import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AreaChart, Area, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { api, ApiError } from '../api/client';
import type { BreakdownItem, DashboardHolding, DashboardOut } from '../api/types';
import {
  fmtINR,
  fmtPct,
  fmtSigned,
  fmtUSD,
  brokerLabel,
  breakdownLabel,
  parseApiTimestamp,
  CHART_COLORS,
} from '../lib/format';
import { invalidatePortfolioQueries } from '../lib/queries';
import { useHighlight } from '../lib/highlight';

const BREAKDOWN_DIMENSIONS: { key: keyof DashboardOut['breakdowns']; title: string }[] = [
  { key: 'by_broker', title: 'By Broker' },
  { key: 'by_asset_class', title: 'By Asset Class' },
  { key: 'by_sector', title: 'By Sector' },
  { key: 'by_region', title: 'India/US' },
];

function Breakdown({ breakdowns }: { breakdowns: DashboardOut['breakdowns'] }) {
  const [dimension, setDimension] = useState<keyof DashboardOut['breakdowns']>('by_broker');
  const items: BreakdownItem[] = breakdowns[dimension] ?? [];

  return (
    <>
      <div className="breakdown-tabs">
        {BREAKDOWN_DIMENSIONS.map((d) => (
          <button
            key={d.key}
            className={`tab-btn ${dimension === d.key ? 'active' : ''}`}
            onClick={() => setDimension(d.key)}
          >
            {d.title}
          </button>
        ))}
      </div>
      <div className="breakdown-body">
        <div className="donut-wrap">
          <PieChart width={150} height={150}>
            <Pie
              data={items}
              dataKey="value_inr"
              nameKey="label"
              cx="50%"
              cy="50%"
              innerRadius={42}
              outerRadius={72}
              startAngle={90}
              endAngle={-270}
              stroke="none"
              isAnimationActive={false}
            >
              {items.map((item, i) => (
                <Cell key={item.label} fill={CHART_COLORS[i % CHART_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value, name) => [fmtINR(Number(value)), breakdownLabel(dimension, String(name))]}
              contentStyle={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                fontSize: 11.5,
              }}
            />
          </PieChart>
        </div>
        <div className="legend">
          {items.map((item, i) => (
            <div className="legend-item" key={item.label}>
              <span className="swatch" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
              {breakdownLabel(dimension, item.label)}
              <span className="val">
                {fmtINR(item.value_inr)} · {item.pct.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function TrajectoryCell({ holding }: { holding: DashboardHolding }) {
  const t = holding.trajectory;

  if (t.static) {
    return (
      <div className="traj-cell">
        <div className="traj-info">
          <span className="traj-stats">Static — priced by you</span>
          <span className="traj-stats" style={{ opacity: 0.75 }}>
            no live feed for manual holdings
          </span>
        </div>
      </div>
    );
  }

  if (t.cold_start) {
    return (
      <div className="traj-cell">
        <div className="traj-info">
          <span className="traj-stats">Gathering history (day {t.days_available} of 30)</span>
        </div>
      </div>
    );
  }

  const chipClass =
    t.flag_kind === 'near_high'
      ? 'badge-gain'
      : t.flag_kind === 'near_low'
        ? 'badge-loss'
        : (holding.today_move_pct ?? 0) >= 0
          ? 'badge-gain'
          : 'badge-loss';

  return (
    <div className="traj-cell">
      <div className="traj-info">
        <span className="traj-stats">
          {t.recent_days}d{' '}
          <span className={(t.recent_return_pct ?? 0) >= 0 ? 'up' : 'down'}>
            {t.recent_return_pct != null ? fmtPct(t.recent_return_pct, 1) : '—'}
          </span>{' '}
          · {t.thirty_day_days}d{' '}
          <span className={(t.thirty_day_return_pct ?? 0) >= 0 ? 'up' : 'down'}>
            {t.thirty_day_return_pct != null ? fmtPct(t.thirty_day_return_pct, 1) : '—'}
          </span>
        </span>
        {t.flag_kind && <span className={`traj-chip badge ${chipClass}`}>{t.flag_text}</span>}
      </div>
    </div>
  );
}

type SortKey = 'symbol' | 'broker' | 'quantity' | 'market_value_inr' | 'pnl_pct';

// Task 32 — zero-ceremony "why I own this" note per holding. Same
// inline-input/blur-to-save pattern as Compass's Risk Controls section
// uses for its stop-loss/target inputs: no modal, no expandable row,
// just one field.
function NotesCell({ holding }: { holding: DashboardHolding }) {
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState(holding.notes ?? '');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setNotes(holding.notes ?? ''), [holding.notes]);

  const saveMutation = useMutation({
    mutationFn: (value: string) => api.updateHoldingNotes(holding.id, { notes: value || null }),
    onSuccess: () => {
      setError(null);
      invalidatePortfolioQueries(queryClient);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Failed to save note.'),
  });

  function commit() {
    if (notes === (holding.notes ?? '')) return;
    saveMutation.mutate(notes);
  }

  return (
    <>
      <input
        type="text"
        className="inline-input notes-input"
        placeholder="Why do you own this?"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur();
        }}
      />
      {error && <div className="hint" style={{ color: 'var(--loss)' }}>{error}</div>}
    </>
  );
}

function HoldingsTable({ holdings }: { holdings: DashboardHolding[] }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'symbol', dir: 1 });
  const { highlightedSymbol, registerRowRef } = useHighlight();

  function toggleSort(key: SortKey) {
    setSort((prev) => (prev.key === key ? { key, dir: (prev.dir * -1) as 1 | -1 } : { key, dir: 1 }));
  }

  const sorted = [...holdings].sort((a, b) => {
    const { key, dir } = sort;
    if (key === 'symbol' || key === 'broker') return dir * a[key].localeCompare(b[key]);
    return dir * (a[key] - b[key]);
  });

  function arrow(key: SortKey) {
    if (sort.key !== key) return null;
    return <span className="sort-arrow">{sort.dir === 1 ? '▲' : '▼'}</span>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table with-traj">
        <thead>
          <tr>
            <th data-sort onClick={() => toggleSort('symbol')}>
              Symbol{arrow('symbol')}
            </th>
            <th data-sort onClick={() => toggleSort('broker')}>
              Broker{arrow('broker')}
            </th>
            <th data-sort className="num" onClick={() => toggleSort('quantity')}>
              Qty{arrow('quantity')}
            </th>
            <th className="num">LTP</th>
            <th data-sort className="num" onClick={() => toggleSort('market_value_inr')}>
              Mkt Value{arrow('market_value_inr')}
            </th>
            <th data-sort className="num" onClick={() => toggleSort('pnl_pct')}>
              P&amp;L{arrow('pnl_pct')}
            </th>
            <th>Trajectory</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((h) => (
            <tr
              key={h.id}
              ref={(el) => registerRowRef(h.symbol, el)}
              className={`${h.threshold_breached ? 'row-breach' : ''}${
                highlightedSymbol === h.symbol ? ' row-ai-highlight' : ''
              }`}
            >
              <td>
                <span className="sym">{h.symbol}</span>
                <div className="sub">{h.exchange}</div>
              </td>
              <td>{brokerLabel(h.broker)}</td>
              <td className="num">{h.quantity}</td>
              <td className="num">{h.currency === 'USD' ? fmtUSD(h.ltp) : fmtINR(h.ltp)}</td>
              <td className="num">{fmtINR(h.market_value_inr)}</td>
              <td className="num">
                <span className={`badge ${h.pnl_pct >= 0 ? 'badge-gain' : 'badge-loss'}`}>
                  {fmtPct(h.pnl_pct, 1)}
                </span>
              </td>
              <td>
                <TrajectoryCell holding={h} />
              </td>
              <td>
                <NotesCell holding={h} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TrendSparkline({ points }: { points: { captured_at: string; total_net_worth_inr: number }[] }) {
  if (points.length < 2) return null;
  return (
    <div className="hero-spark">
      <div style={{ width: 140, height: 42 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
            <defs>
              <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <Tooltip
              formatter={(value) => fmtINR(Number(value))}
              labelFormatter={(_, payload) =>
                payload?.[0]?.payload
                  ? parseApiTimestamp(payload[0].payload.captured_at as string).toLocaleString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : ''
              }
              contentStyle={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                fontSize: 11.5,
              }}
            />
            <Area
              type="monotone"
              dataKey="total_net_worth_inr"
              stroke="var(--accent)"
              strokeWidth={1.6}
              fill="url(#sparkFill)"
              dot={false}
              activeDot={{ r: 2.6 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="sub" style={{ margin: '4px 0 0', textAlign: 'right' }}>
        30-day trend
      </p>
    </div>
  );
}

export function Dashboard() {
  const queryClient = useQueryClient();
  const [toastMsg, setToastMsg] = useState('');
  const [toastVisible, setToastVisible] = useState(false);
  const toastTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  function showToast(msg: string) {
    setToastMsg(msg);
    setToastVisible(true);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastVisible(false), 2600);
  }

  const dashboardQuery = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard });
  const trendQuery = useQuery({ queryKey: ['trend', 30], queryFn: () => api.trend(30) });
  const alertsQuery = useQuery({ queryKey: ['alerts'], queryFn: api.alerts });
  const riskQuery = useQuery({ queryKey: ['risk'], queryFn: api.risk });

  const refreshMutation = useMutation({
    mutationFn: api.refresh,
    onSuccess: (data) => {
      invalidatePortfolioQueries(queryClient);
      const entries = Object.entries(data.results);
      const failed = entries.filter(([, r]) => !r.ok);
      const okCount = entries.length - failed.length;
      showToast(
        failed.length === 0
          ? `Synced ${okCount} source${okCount === 1 ? '' : 's'}`
          : `Synced ${okCount}/${entries.length} sources — ${failed.map(([b]) => brokerLabel(b)).join(', ')} failed`,
      );
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 429) {
        showToast(err.message);
      } else {
        showToast('Refresh failed — check bridge-server.');
      }
    },
  });

  const isLoading =
    dashboardQuery.isLoading || trendQuery.isLoading || alertsQuery.isLoading || riskQuery.isLoading;
  const isError = dashboardQuery.isError || trendQuery.isError || alertsQuery.isError || riskQuery.isError;

  return (
    <>
      <div className="topbar">
        <div>
          <h1 className="topbar-title">Dashboard</h1>
          <p className="topbar-sub">Consolidated view across both brokers</p>
        </div>
        <div className="topbar-actions">
          <button
            className="btn btn-primary"
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
          >
            {refreshMutation.isPending ? (
              <>
                <span className="spin" /> Refreshing…
              </>
            ) : (
              'Refresh'
            )}
          </button>
        </div>
      </div>

      {isLoading && <p className="loading-state">Loading dashboard…</p>}
      {!isLoading && isError && (
        <p className="error-state">Can't reach bridge-server at the configured API URL.</p>
      )}

      {!isLoading && !isError && dashboardQuery.data && riskQuery.data && alertsQuery.data && (
        <div className="stack" style={{ marginTop: 20 }}>
          <div className="grid-2">
            <div className="card hero-card">
              <div className="hero-top">
                <div>
                  <p className="hero-label">Net Worth</p>
                  <p className="hero-figure mono">{fmtINR(dashboardQuery.data.net_worth_inr)}</p>
                  <span
                    className={`hero-delta ${dashboardQuery.data.today_move_abs_inr >= 0 ? 'delta-up' : 'delta-down'}`}
                  >
                    {dashboardQuery.data.today_move_abs_inr >= 0 ? '▲' : '▼'}{' '}
                    {fmtSigned(dashboardQuery.data.today_move_abs_inr)} ({fmtPct(dashboardQuery.data.today_move_pct)})
                    today
                  </span>
                </div>
                {trendQuery.data && <TrendSparkline points={trendQuery.data.points} />}
              </div>
            </div>

            <div className="card">
              <p className="card-title">Alerts · What to look at today</p>
              <div className="alerts-list">
                {alertsQuery.data.alerts.length ? (
                  alertsQuery.data.alerts.map((alert, i) => (
                    <div className="alert-item" key={i}>
                      <span className={`alert-stripe ${alert.severity}`} />
                      <div className="alert-body">
                        <p className="alert-title">{alert.title}</p>
                        <p className="alert-meta">
                          {brokerLabel(alert.broker)} · {alert.symbol}
                        </p>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="alert-empty">Nothing flagged — no thresholds breached, no unusual moves today.</p>
                )}
              </div>
            </div>
          </div>

          <div className="card">
            <p className="card-title">Risk &amp; Concentration</p>
            <div className="risk-list">
              {riskQuery.data.concentration_flags.length ? (
                riskQuery.data.concentration_flags.map((flag) => (
                  <div className="risk-flag" key={`${flag.kind}-${flag.label}`}>
                    <span>
                      {flag.kind === 'stock'
                        ? `${flag.label} is ${flag.pct.toFixed(1)}% of net worth`
                        : `${flag.label} sector is ${flag.pct.toFixed(1)}% of net worth`}
                    </span>
                    <span className="badge badge-warn">limit {flag.limit_pct}%</span>
                  </div>
                ))
              ) : (
                <div className="risk-flag">
                  <span>No concentration flags right now.</span>
                </div>
              )}
            </div>
            <div className="allocation-block">
              <div className="allocation-labels">
                <span>India {riskQuery.data.region_split.india_pct.toFixed(1)}%</span>
                {riskQuery.data.region_split.target_india_pct != null && (
                  <span>
                    Target {riskQuery.data.region_split.target_india_pct}/
                    {riskQuery.data.region_split.target_us_pct}
                  </span>
                )}
                <span>US {riskQuery.data.region_split.us_pct.toFixed(1)}%</span>
              </div>
              <div className="allocation-bar">
                <div
                  className="allocation-seg seg-india"
                  style={{ width: `${riskQuery.data.region_split.india_pct}%` }}
                />
                <div
                  className="allocation-seg seg-us"
                  style={{ width: `${riskQuery.data.region_split.us_pct}%` }}
                />
                {riskQuery.data.region_split.target_india_pct != null && (
                  <div
                    className="target-tick"
                    style={{ left: `${riskQuery.data.region_split.target_india_pct}%` }}
                  />
                )}
              </div>
              {riskQuery.data.region_split.drift_pct != null && (
                <p className="sub" style={{ margin: '6px 0 0' }}>
                  Drift from target: {fmtPct(riskQuery.data.region_split.drift_pct, 1)}
                </p>
              )}
            </div>
          </div>

          <div className="card">
            <p className="card-title">
              <span>Breakdown</span>
              <span className="mono">
                Total P&amp;L: {fmtSigned(dashboardQuery.data.total_pnl_abs_inr)} (
                {fmtPct(dashboardQuery.data.total_pnl_pct)})
              </span>
            </p>
            <Breakdown breakdowns={dashboardQuery.data.breakdowns} />
          </div>

          <div className="card">
            <p className="card-title">Holdings</p>
            <HoldingsTable holdings={dashboardQuery.data.holdings} />
          </div>
        </div>
      )}

      <div id="toast" className={toastVisible ? 'show' : ''}>
        {toastMsg}
      </div>
    </>
  );
}
