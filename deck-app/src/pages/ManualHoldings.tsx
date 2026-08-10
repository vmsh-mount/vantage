import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';
import type { CsvImportOut, DashboardHolding, ManualHoldingIn } from '../api/types';
import { fmtUSD } from '../lib/format';
import { invalidatePortfolioQueries } from '../lib/queries';

interface FormValues {
  symbol: string;
  quantity: string;
  avgCost: string;
  sector: string;
  exchange: string;
  repriceTo: string;
}

const EMPTY_FORM: FormValues = { symbol: '', quantity: '', avgCost: '', sector: '', exchange: 'NASDAQ', repriceTo: '' };

function holdingToForm(h: DashboardHolding): FormValues {
  return {
    symbol: h.symbol,
    quantity: String(h.quantity),
    avgCost: String(h.avg_cost),
    sector: h.sector ?? '',
    exchange: h.exchange,
    repriceTo: '',
  };
}

function buildPayload(values: FormValues): ManualHoldingIn | null {
  const quantity = parseFloat(values.quantity);
  const avg_cost = parseFloat(values.avgCost);
  if (!values.symbol.trim() || !(quantity > 0) || !(avg_cost > 0)) return null;
  const payload: ManualHoldingIn = {
    symbol: values.symbol.trim().toUpperCase(),
    quantity,
    avg_cost,
    sector: values.sector.trim() || undefined,
    exchange: values.exchange.trim().toUpperCase() || 'NASDAQ',
  };
  if (values.repriceTo.trim()) {
    const ltp = parseFloat(values.repriceTo);
    if (ltp > 0) payload.ltp = ltp;
  }
  return payload;
}

function HoldingFormPanel({
  mode,
  initial,
  currentLtp,
  onSubmit,
  onCancel,
  pending,
  error,
}: {
  mode: 'add' | 'edit';
  initial: FormValues;
  currentLtp?: number;
  onSubmit: (payload: ManualHoldingIn) => void;
  onCancel: () => void;
  pending: boolean;
  error: string | null;
}) {
  const [values, setValues] = useState(initial);
  const [localError, setLocalError] = useState<string | null>(null);

  function set<K extends keyof FormValues>(key: K, v: string) {
    setValues((prev) => ({ ...prev, [key]: v }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = buildPayload(values);
    if (!payload) {
      setLocalError('Symbol, quantity, and avg cost are required — quantity and avg cost must be positive.');
      return;
    }
    setLocalError(null);
    onSubmit(payload);
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-row">
        <div className="field">
          <label>Symbol</label>
          <input type="text" placeholder="GOOGL" value={values.symbol} onChange={(e) => set('symbol', e.target.value)} />
        </div>
        <div className="field">
          <label>Qty</label>
          <input type="number" placeholder="3" value={values.quantity} onChange={(e) => set('quantity', e.target.value)} />
        </div>
        <div className="field">
          <label>Avg Cost (USD)</label>
          <input type="number" placeholder="142.50" value={values.avgCost} onChange={(e) => set('avgCost', e.target.value)} />
        </div>
        <div className="field">
          <label>Sector</label>
          <input type="text" placeholder="Technology" value={values.sector} onChange={(e) => set('sector', e.target.value)} />
        </div>
        <div className="field">
          <label>Exchange</label>
          <input type="text" placeholder="NASDAQ" value={values.exchange} onChange={(e) => set('exchange', e.target.value)} />
        </div>
        <div className="field">
          <button className="btn btn-primary" type="submit" disabled={pending}>
            {pending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {mode === 'edit' && (
        <div className="field" style={{ maxWidth: 320, marginTop: 12 }}>
          <label>Reprice — current price is {currentLtp != null ? fmtUSD(currentLtp) : '—'}</label>
          <input
            type="number"
            placeholder="Leave blank to keep current price"
            value={values.repriceTo}
            onChange={(e) => set('repriceTo', e.target.value)}
          />
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 10 }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
          Cancel
        </button>
        {(localError || error) && <p className="error-state" style={{ padding: 0, margin: 0 }}>{localError || error}</p>}
      </div>
    </form>
  );
}

function ManualHoldingsTable({ holdings }: { holdings: DashboardHolding[] }) {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  function invalidate() {
    invalidatePortfolioQueries(queryClient);
  }

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ManualHoldingIn }) => api.updateManualHolding(id, payload),
    onSuccess: () => {
      setEditingId(null);
      setMutationError(null);
      invalidate();
    },
    onError: (err) => setMutationError(err instanceof ApiError ? err.message : 'Failed to update holding.'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteManualHolding(id),
    onSuccess: () => invalidate(),
  });

  if (holdings.length === 0) {
    return <p className="alert-empty">No manual holdings yet — add one below or import a CSV.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th className="num">Qty</th>
            <th className="num">Avg Cost</th>
            <th>Sector</th>
            <th className="num">Current Price</th>
            <th className="num">Market Value</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) =>
            editingId === h.id ? (
              <tr key={h.id}>
                <td colSpan={7}>
                  <HoldingFormPanel
                    mode="edit"
                    initial={holdingToForm(h)}
                    currentLtp={h.ltp}
                    pending={updateMutation.isPending}
                    error={mutationError}
                    onCancel={() => {
                      setEditingId(null);
                      setMutationError(null);
                    }}
                    onSubmit={(payload) => updateMutation.mutate({ id: h.id, payload })}
                  />
                </td>
              </tr>
            ) : (
              <tr key={h.id}>
                <td>
                  <span className="sym">{h.symbol}</span>
                  <div className="sub">{h.exchange}</div>
                </td>
                <td className="num">{h.quantity}</td>
                <td className="num">{fmtUSD(h.avg_cost)}</td>
                <td>{h.sector ?? '—'}</td>
                <td className="num">{fmtUSD(h.ltp)}</td>
                <td className="num">{fmtUSD(h.quantity * h.ltp)}</td>
                <td style={{ textAlign: 'right' }}>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      setMutationError(null);
                      setEditingId(h.id);
                    }}
                  >
                    Edit
                  </button>{' '}
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      if (window.confirm(`Delete ${h.symbol}? This can't be undone.`)) {
                        deleteMutation.mutate(h.id);
                      }
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
    </div>
  );
}

function CsvImportBox() {
  const queryClient = useQueryClient();
  const [raw, setRaw] = useState('');
  const [preview, setPreview] = useState<{ symbol: string; qty: number; cost: number; sector: string; valid: boolean }[] | null>(
    null,
  );
  const [result, setResult] = useState<CsvImportOut | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const importMutation = useMutation({
    mutationFn: (csv: string) => api.importCsv(csv),
    onSuccess: (data) => {
      setResult(data);
      setImportError(null);
      setPreview(null);
      setRaw('');
      invalidatePortfolioQueries(queryClient);
    },
    onError: (err) => setImportError(err instanceof ApiError ? err.message : 'Failed to import CSV.'),
  });

  function handlePreview() {
    setResult(null);
    const rows = raw
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split(',').map((s) => s.trim());
        const symbol = (parts[0] ?? '').toUpperCase();
        const qty = parseFloat(parts[1] ?? '');
        const cost = parseFloat(parts[2] ?? '');
        const sector = parts[3] || 'Uncategorized';
        return { symbol, qty, cost, sector, valid: !!symbol && qty > 0 && cost > 0 };
      });
    setPreview(rows);
  }

  return (
    <div className="csv-box">
      <p className="card-title" style={{ marginBottom: 8 }}>
        Import from INDmoney CSV export
      </p>
      <textarea
        placeholder={'Paste exported rows, e.g.\nGOOGL,3,142.50,Technology\nAMZN,5,178.20,Consumer'}
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          setPreview(null);
          setResult(null);
          setImportError(null);
        }}
      />
      <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
        <button className="btn" type="button" onClick={handlePreview} disabled={!raw.trim()}>
          Preview import
        </button>
        {preview && preview.length > 0 && (
          <button
            className="btn btn-primary"
            type="button"
            onClick={() => importMutation.mutate(raw)}
            disabled={importMutation.isPending}
          >
            {importMutation.isPending ? 'Importing…' : 'Confirm import'}
          </button>
        )}
        {importError && <p className="error-state" style={{ padding: 0, margin: 0 }}>{importError}</p>}
      </div>

      {preview && (
        <div className={`csv-preview ${preview.length ? 'open' : ''}`}>
          {preview.length === 0 ? (
            <p className="hint">No rows found — check the format.</p>
          ) : (
            <div className="table-wrap" style={{ marginTop: 10 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th className="num">Qty</th>
                    <th className="num">Avg Cost</th>
                    <th>Sector</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.map((r, i) => (
                    <tr key={i} className={r.valid ? '' : 'row-breach'}>
                      <td>{r.symbol || '—'}</td>
                      <td className="num">{Number.isFinite(r.qty) ? r.qty : '—'}</td>
                      <td className="num">{Number.isFinite(r.cost) ? fmtUSD(r.cost) : '—'}</td>
                      <td>{r.sector}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="hint">
                This is a client-side preview — final validation happens on import. Rows highlighted red look
                malformed and will likely be skipped.
              </p>
            </div>
          )}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 14 }}>
          {result.imported.length > 0 && (
            <p className="hint" style={{ color: 'var(--gain)' }}>
              Imported {result.imported.length}: {result.imported.map((h) => h.symbol).join(', ')}
            </p>
          )}
          {result.skipped.length > 0 && (
            <div>
              <p className="hint" style={{ color: 'var(--loss)' }}>
                Skipped {result.skipped.length}:
              </p>
              <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                {result.skipped.map((s) => (
                  <li key={s.line_number} className="hint">
                    Line {s.line_number}: {s.reason} — <span className="mono">{s.raw}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <p className="hint">Format: symbol, qty, avg cost (USD), sector — one holding per line.</p>
    </div>
  );
}

export function ManualHoldings() {
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const dashboardQuery = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard });

  const createMutation = useMutation({
    mutationFn: (payload: ManualHoldingIn) => api.createManualHolding(payload),
    onSuccess: () => {
      setShowAddForm(false);
      setAddError(null);
      invalidatePortfolioQueries(queryClient);
    },
    onError: (err) => setAddError(err instanceof ApiError ? err.message : 'Failed to create holding.'),
  });

  const manualHoldings = dashboardQuery.data?.holdings.filter((h) => h.source === 'manual') ?? [];

  return (
    <>
      <div className="topbar">
        <div>
          <h1 className="topbar-title">Manual Holdings</h1>
          <p className="topbar-sub">US positions from INDmoney, entered by hand</p>
        </div>
      </div>

      {dashboardQuery.isLoading && <p className="loading-state">Loading…</p>}
      {dashboardQuery.isError && <p className="error-state">Can't reach bridge-server at the configured API URL.</p>}

      {dashboardQuery.data && (
        <div className="card" style={{ marginTop: 20 }}>
          <p className="card-title">
            <span>US Holdings (INDmoney) · entered manually, no official API for these</span>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => {
                setAddError(null);
                setShowAddForm((v) => !v);
              }}
            >
              {showAddForm ? 'Close' : '+ Add holding'}
            </button>
          </p>

          {showAddForm && (
            <div style={{ marginBottom: 16 }}>
              <HoldingFormPanel
                mode="add"
                initial={EMPTY_FORM}
                pending={createMutation.isPending}
                error={addError}
                onCancel={() => {
                  setShowAddForm(false);
                  setAddError(null);
                }}
                onSubmit={(payload) => createMutation.mutate(payload)}
              />
            </div>
          )}

          <ManualHoldingsTable holdings={manualHoldings} />

          <CsvImportBox />
        </div>
      )}
    </>
  );
}
