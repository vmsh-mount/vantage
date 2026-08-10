import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';
import type { BrokerStatus, QuarantinedDecision, QuarantinedThesis } from '../api/types';
import { brokerLabel, relativeTime } from '../lib/format';
import { invalidatePortfolioQueries } from '../lib/queries';

const BROKER_DESCRIPTION: Record<string, string> = {
  paytmmoney: 'Trading API · key + secret + session token',
  indmoney: 'INDstocks API · KYC + access token',
};

function BrokerCard({ status }: { status: BrokerStatus }) {
  const badgeClass = !status.healthy ? 'badge-expired' : status.mode === 'live' ? 'badge-live' : 'badge-mock';
  const badgeText = !status.healthy ? 'UNHEALTHY' : status.mode === 'live' ? 'LIVE' : 'MOCK';

  return (
    <div className="card status-card">
      <div className="status-head">
        <p className="status-name">{brokerLabel(status.broker)}</p>
        <span className={`badge ${badgeClass}`}>{badgeText}</span>
      </div>
      <p className="status-meta">{BROKER_DESCRIPTION[status.broker] ?? status.broker}</p>
      <p className="status-meta">
        Last sync: {status.last_sync_at ? relativeTime(status.last_sync_at) : 'never'}
      </p>
      {status.warning && <div className="warning-banner show">{status.warning}</div>}
    </div>
  );
}

// Task 35 — memory-poisoning defenses. Deliberately small: a row here means
// a session that touched untrusted web content also wrote a thesis/decision
// entry — already excluded from every agent-facing read by default, this is
// just the human "look at it, then let it back in" surface. Expected to be
// empty almost always.
function QuarantineSection() {
  const queryClient = useQueryClient();
  const quarantineQuery = useQuery({ queryKey: ['quarantine'], queryFn: api.quarantine });

  const reviewMutation = useMutation({
    mutationFn: ({ table, id }: { table: string; id: number }) => api.reviewQuarantined(table, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['quarantine'] }),
  });

  const theses = quarantineQuery.data?.theses ?? [];
  const decisions = quarantineQuery.data?.decisions ?? [];
  const total = theses.length + decisions.length;

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="status-head">
        <p className="status-name">Memory quarantine</p>
        {total > 0 && <span className="badge badge-expired">{total}</span>}
      </div>
      <p className="status-meta">
        Thesis/decision entries written by a session that also touched untrusted web content —
        held back from the agent's own reads until reviewed.
      </p>

      {quarantineQuery.isLoading && <p className="loading-state">Loading…</p>}
      {quarantineQuery.isError && <p className="error-state">Can't reach bridge-server.</p>}

      {quarantineQuery.data && total === 0 && (
        <p className="status-meta" style={{ marginTop: 8 }}>
          Nothing quarantined.
        </p>
      )}

      {theses.map((t: QuarantinedThesis) => (
        <div key={`thesis-${t.id}`} className="status-meta" style={{ marginTop: 8 }}>
          <strong>{brokerLabel(t.broker)}</strong> {t.symbol} — thesis: "{t.text}"
          {' · '}
          {relativeTime(t.created_at)}{' '}
          <button
            className="btn btn-sm"
            disabled={reviewMutation.isPending}
            onClick={() => reviewMutation.mutate({ table: 'theses', id: t.id })}
          >
            Mark reviewed
          </button>
        </div>
      ))}

      {decisions.map((d: QuarantinedDecision) => (
        <div key={`decision-${d.id}`} className="status-meta" style={{ marginTop: 8 }}>
          <strong>{brokerLabel(d.broker)}</strong> {d.symbol} — decision: "{d.headline}"
          {' · '}
          {relativeTime(d.created_at)}{' '}
          <button
            className="btn btn-sm"
            disabled={reviewMutation.isPending}
            onClick={() => reviewMutation.mutate({ table: 'decision_log', id: d.id })}
          >
            Mark reviewed
          </button>
        </div>
      ))}
    </div>
  );
}

export function Status() {
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

  const statusQuery = useQuery({ queryKey: ['status'], queryFn: api.status });

  const refreshMutation = useMutation({
    mutationFn: api.refresh,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['status'] });
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
        showToast('Already refreshing — hang on.');
      } else {
        showToast('Refresh failed — check bridge-server.');
      }
    },
  });

  return (
    <>
      <div className="topbar">
        <div>
          <h1 className="topbar-title">Status</h1>
          <p className="topbar-sub">Per-broker sync health and token state</p>
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
              'Refresh now'
            )}
          </button>
        </div>
      </div>

      {statusQuery.isLoading && <p className="loading-state">Loading…</p>}
      {statusQuery.isError && <p className="error-state">Can't reach bridge-server at the configured API URL.</p>}

      {statusQuery.data && (
        <div className="grid-2b" style={{ marginTop: 20 }}>
          {statusQuery.data.brokers.map((status) => (
            <BrokerCard key={status.broker} status={status} />
          ))}
        </div>
      )}

      <QuarantineSection />

      <div id="toast" className={toastVisible ? 'show' : ''}>
        {toastMsg}
      </div>
    </>
  );
}
