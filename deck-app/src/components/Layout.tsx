import { NavLink, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { AiPanel } from './AiPanel';
import { HighlightProvider } from '../lib/highlight';

const NAV_ITEMS = [
  {
    to: '/',
    label: 'Dashboard',
    icon: (
      <svg viewBox="0 0 20 20">
        <rect x="2" y="2" width="7" height="7" rx="1.5" />
        <rect x="11" y="2" width="7" height="7" rx="1.5" />
        <rect x="2" y="11" width="7" height="7" rx="1.5" />
        <rect x="11" y="11" width="7" height="7" rx="1.5" />
      </svg>
    ),
  },
  {
    to: '/manual-holdings',
    label: 'Manual Holdings',
    icon: (
      <svg viewBox="0 0 20 20">
        <line x1="3" y1="5" x2="17" y2="5" />
        <line x1="3" y1="10" x2="17" y2="10" />
        <line x1="3" y1="15" x2="11" y2="15" />
        <circle cx="15.5" cy="15" r="1.7" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
  {
    to: '/compass',
    label: 'Compass',
    icon: (
      <svg viewBox="0 0 20 20">
        <circle cx="10" cy="10" r="7.5" />
        <path d="M12.8 7.2l-1.8 4.3-4.3 1.8 1.8-4.3z" />
      </svg>
    ),
  },
  {
    to: '/status',
    label: 'Status',
    icon: (
      <svg viewBox="0 0 20 20">
        <polyline points="2,11 6,11 8,4 12,17 14,11 18,11" />
      </svg>
    ),
  },
];

export function Layout() {
  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: api.status,
    staleTime: 60_000,
  });

  return (
    <HighlightProvider>
      <div className="app">
        <nav className="rail">
          <div className="brand">
            <p className="brand-title">Vantage</p>
            <p className="brand-sub">personal capital ledger</p>
          </div>
          <ul className="nav">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span className="nav-label">{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="nav-footer">
            <div className="rail-status">
              {status?.brokers.map((broker) => (
                <span key={broker.broker}>
                  <span className={`dot ${broker.mode === 'live' ? 'dot-live' : 'dot-mock'}`} />
                  {broker.broker === 'paytmmoney' ? 'PaytmMoney' : 'INDmoney'}
                </span>
              ))}
            </div>
            <p className="nav-footer-text">
              Local, single-user portfolio dashboard.
              <br />
              Read-only — never places trades.
            </p>
          </div>
        </nav>
        <div className="main">
          <div className="viewport">
            <div className="page">
              <Outlet />
            </div>
          </div>
        </div>
        <AiPanel />
      </div>
    </HighlightProvider>
  );
}
