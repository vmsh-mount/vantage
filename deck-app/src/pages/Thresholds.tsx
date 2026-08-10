import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';
import type { ThresholdIn, ThresholdListItem } from '../api/types';
import { brokerLabel } from '../lib/format';
import { invalidatePortfolioQueries } from '../lib/queries';

function invalidateRiskDependent(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ['thresholds'] });
  invalidatePortfolioQueries(queryClient);
}

function ThresholdRow({ item }: { item: ThresholdListItem }) {
  const queryClient = useQueryClient();
  const [stopLoss, setStopLoss] = useState(item.stop_loss_pct != null ? String(item.stop_loss_pct) : '');
  const [target, setTarget] = useState(item.target_pct != null ? String(item.target_pct) : '');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStopLoss(item.stop_loss_pct != null ? String(item.stop_loss_pct) : '');
    setTarget(item.target_pct != null ? String(item.target_pct) : '');
  }, [item.stop_loss_pct, item.target_pct]);

  const saveMutation = useMutation({
    mutationFn: (payload: ThresholdIn) => api.updateThreshold(payload),
    onSuccess: () => {
      setError(null);
      invalidateRiskDependent(queryClient);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Failed to save threshold.'),
  });

  const clearMutation = useMutation({
    mutationFn: () => api.deleteThreshold(item.broker, item.symbol),
    onSuccess: () => {
      setError(null);
      invalidateRiskDependent(queryClient);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Failed to clear threshold.'),
  });

  function commit() {
    const slRaw = stopLoss.trim();
    const tgRaw = target.trim();
    const hadStopLoss = item.stop_loss_pct != null;
    const hadTarget = item.target_pct != null;

    if (slRaw === '' && hadStopLoss) {
      setError(
        hadTarget
          ? 'Clear removes both stop-loss and target for this holding — set a new negative value instead if you just want to update it.'
          : 'Clear removes the stop-loss, or set a new negative value.',
      );
      return;
    }
    if (tgRaw === '' && hadTarget) {
      setError(
        hadStopLoss
          ? 'Clear removes both stop-loss and target for this holding — set a new positive value instead if you just want to update it.'
          : 'Clear removes the target, or set a new positive value.',
      );
      return;
    }
    if (slRaw === '' && tgRaw === '') return;

    const sl = slRaw === '' ? null : parseFloat(slRaw);
    const tg = tgRaw === '' ? null : parseFloat(tgRaw);

    if (sl != null && (Number.isNaN(sl) || sl >= 0)) {
      setError('Stop-loss must be a negative number, e.g. -10.');
      return;
    }
    if (tg != null && (Number.isNaN(tg) || tg <= 0)) {
      setError('Target must be a positive number, e.g. 20.');
      return;
    }
    if (sl === item.stop_loss_pct && tg === item.target_pct) return;

    setError(null);
    saveMutation.mutate({ broker: item.broker, symbol: item.symbol, stop_loss_pct: sl, target_pct: tg });
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') e.currentTarget.blur();
  }

  const hasAnyThreshold = item.stop_loss_pct != null || item.target_pct != null;

  return (
    <>
      <tr>
        <td>
          <span className="sym">{item.symbol}</span>
          <div className="sub">{brokerLabel(item.broker)}</div>
        </td>
        <td className="num">
          <input
            type="number"
            className="inline-input"
            max={-0.01}
            step={0.1}
            placeholder="—"
            value={stopLoss}
            onChange={(e) => setStopLoss(e.target.value)}
            onBlur={commit}
            onKeyDown={onKeyDown}
          />{' '}
          %
        </td>
        <td className="num">
          <input
            type="number"
            className="inline-input"
            min={0.01}
            step={0.1}
            placeholder="—"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            onBlur={commit}
            onKeyDown={onKeyDown}
          />{' '}
          %
        </td>
        <td style={{ textAlign: 'right' }}>
          <button
            className="btn btn-ghost btn-sm"
            disabled={!hasAnyThreshold || clearMutation.isPending}
            onClick={() => clearMutation.mutate()}
          >
            Clear
          </button>
        </td>
      </tr>
      {error && (
        <tr>
          <td colSpan={4} style={{ padding: '0 14px 8px' }}>
            <p className="error-state" style={{ padding: 0 }}>
              {error}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

function ThresholdsTable() {
  const query = useQuery({ queryKey: ['thresholds'], queryFn: api.thresholds });

  if (query.isLoading) return <p className="loading-state">Loading…</p>;
  if (query.isError) return <p className="error-state">Can't reach bridge-server at the configured API URL.</p>;

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Holding</th>
            <th className="num">Stop-Loss</th>
            <th className="num">Target</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {query.data?.thresholds.map((item) => (
            <ThresholdRow key={`${item.broker}:${item.symbol}`} item={item} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RiskSettingsPanel() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ['riskSettings'], queryFn: api.riskSettings });

  const [stockPct, setStockPct] = useState(15);
  const [sectorPct, setSectorPct] = useState(30);
  const [targetIndia, setTargetIndia] = useState(50);
  const [targetTouched, setTargetTouched] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSaved, setShowSaved] = useState(false);

  useEffect(() => {
    if (settingsQuery.data && !initialized) {
      setStockPct(settingsQuery.data.concentration_stock_pct);
      setSectorPct(settingsQuery.data.concentration_sector_pct);
      setTargetIndia(settingsQuery.data.target_india_pct ?? 50);
      setInitialized(true);
    }
  }, [settingsQuery.data, initialized]);

  const hasTarget = settingsQuery.data?.target_india_pct != null || targetTouched;

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateRiskSettings({
        concentration_stock_pct: stockPct,
        concentration_sector_pct: sectorPct,
        ...(hasTarget ? { target_india_pct: targetIndia } : {}),
      }),
    onSuccess: () => {
      setError(null);
      setShowSaved(true);
      window.setTimeout(() => setShowSaved(false), 2000);
      queryClient.invalidateQueries({ queryKey: ['riskSettings'] });
      queryClient.invalidateQueries({ queryKey: ['risk'] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Failed to save risk settings.'),
  });

  if (settingsQuery.isLoading) return <p className="loading-state">Loading…</p>;
  if (settingsQuery.isError) return <p className="error-state">Can't reach bridge-server at the configured API URL.</p>;

  return (
    <div className="settings-grid">
      <div className="setting-item">
        <label>
          Single-stock concentration limit — <span className="setting-value">{stockPct}%</span>
        </label>
        <input
          type="range"
          min={5}
          max={40}
          value={stockPct}
          onChange={(e) => setStockPct(Number(e.target.value))}
        />
      </div>
      <div className="setting-item">
        <label>
          Sector concentration limit — <span className="setting-value">{sectorPct}%</span>
        </label>
        <input
          type="range"
          min={10}
          max={60}
          value={sectorPct}
          onChange={(e) => setSectorPct(Number(e.target.value))}
        />
      </div>
      <div className="setting-item">
        <label>
          Target allocation —{' '}
          <span className="setting-value">
            {hasTarget ? `India ${targetIndia}% / US ${100 - targetIndia}%` : 'not set'}
          </span>
        </label>
        <input
          type="range"
          min={0}
          max={100}
          value={targetIndia}
          onChange={(e) => {
            setTargetIndia(Number(e.target.value));
            setTargetTouched(true);
          }}
        />
      </div>

      <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 10, alignItems: 'center' }}>
        <button className="btn btn-primary btn-sm" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
          {saveMutation.isPending ? 'Saving…' : 'Save risk settings'}
        </button>
        {showSaved && !error && <span className="hint">Saved.</span>}
        {error && <p className="error-state" style={{ padding: 0, margin: 0 }}>{error}</p>}
      </div>
    </div>
  );
}

export function Thresholds() {
  return (
    <>
      <div className="topbar">
        <div>
          <h1 className="topbar-title">Thresholds</h1>
          <p className="topbar-sub">Your own stop-loss / target lines, independent of the broker</p>
        </div>
      </div>

      <div className="stack" style={{ marginTop: 20 }}>
        <div className="card">
          <p className="card-title">Risk Settings</p>
          <RiskSettingsPanel />
        </div>

        <div className="card">
          <p className="card-title">Per-Holding Stop-Loss / Target</p>
          <ThresholdsTable />
          <p className="footnote">Independent of any broker-side alerts — these thresholds are yours.</p>
        </div>
      </div>
    </>
  );
}
