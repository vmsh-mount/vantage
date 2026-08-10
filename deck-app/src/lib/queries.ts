import type { QueryClient } from '@tanstack/react-query';

// The shared "portfolio data changed" set: anything that adds/edits/removes a
// holding or a threshold can move net worth, breakdowns, concentration flags,
// the region split, or trigger/clear a stop-loss alert. Centralized so a new
// mutation on any page can't silently forget one of these — a real gap here
// (task 16 originally only invalidated 'dashboard') is invisible in-page
// since no single page's own testing round-trips through another page's
// queries; only a cross-page walkthrough (task 19) surfaces it.
export function invalidatePortfolioQueries(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  queryClient.invalidateQueries({ queryKey: ['trend'] });
  queryClient.invalidateQueries({ queryKey: ['alerts'] });
  queryClient.invalidateQueries({ queryKey: ['risk'] });
}
