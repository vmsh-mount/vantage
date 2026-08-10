export function fmtINR(n: number): string {
  return '₹' + Math.round(n).toLocaleString('en-IN');
}

export function fmtSigned(n: number): string {
  return (n >= 0 ? '+₹' : '-₹') + Math.round(Math.abs(n)).toLocaleString('en-IN');
}

export function fmtPct(n: number, digits = 2): string {
  return (n >= 0 ? '+' : '') + n.toFixed(digits) + '%';
}

export function fmtUSD(n: number): string {
  return '$' + n.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

export function brokerLabel(broker: string): string {
  if (broker === 'paytmmoney') return 'PaytmMoney';
  if (broker === 'indmoney') return 'INDmoney';
  return broker;
}

export function assetClassLabel(assetClass: string): string {
  if (assetClass === 'india_equity') return 'India Equity';
  if (assetClass === 'us_equity') return 'US Equity';
  return assetClass;
}

export function regionLabel(region: string): string {
  return region === 'us' ? 'United States' : region === 'india' ? 'India' : region;
}

export function breakdownLabel(dimension: string, label: string): string {
  if (dimension === 'by_broker') return brokerLabel(label);
  if (dimension === 'by_asset_class') return assetClassLabel(label);
  if (dimension === 'by_region') return regionLabel(label);
  return label;
}

// bridge-server serializes naive UTC timestamps (no trailing "Z"/offset). A
// bare "T"-form date-time string is parsed as *local* time per the JS Date
// spec, so every API timestamp must go through this before use — appending
// "Z" ourselves is the only thing forcing the correct UTC interpretation.
export function parseApiTimestamp(isoUtc: string): Date {
  return new Date(isoUtc.endsWith('Z') ? isoUtc : `${isoUtc}Z`);
}

export function relativeTime(isoUtc: string): string {
  const then = parseApiTimestamp(isoUtc).getTime();
  const diffSeconds = Math.round((Date.now() - then) / 1000);

  if (diffSeconds < 5) return 'just now';
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
}

export const CHART_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
];
