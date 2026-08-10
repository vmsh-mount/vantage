// Task 29 — backs the one real "UI action" (highlight_holding, task 26's
// vantage_mcp.py). The panel calls highlightHolding() when it sees that
// tool_use event stream past; Dashboard's holdings table registers each
// row's DOM node so it can be scrolled into view and briefly highlighted.
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';

interface HighlightState {
  highlightedSymbol: string | null;
  highlightHolding: (symbol: string) => void;
  registerRowRef: (symbol: string, el: HTMLElement | null) => void;
}

const HighlightContext = createContext<HighlightState | null>(null);

// Long enough for a user to actually notice a subtle background-color
// change while they're reading the panel's response, not just glance back
// in time to catch a flash.
const HIGHLIGHT_DURATION_MS = 8000;

export function HighlightProvider({ children }: { children: ReactNode }) {
  const [highlightedSymbol, setHighlightedSymbol] = useState<string | null>(null);
  const rowRefs = useRef<Record<string, HTMLElement>>({});
  const clearTimer = useRef<number | null>(null);

  const registerRowRef = useCallback((symbol: string, el: HTMLElement | null) => {
    if (el) rowRefs.current[symbol] = el;
    else delete rowRefs.current[symbol];
  }, []);

  const highlightHolding = useCallback((symbol: string) => {
    setHighlightedSymbol(symbol);
    rowRefs.current[symbol]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (clearTimer.current) window.clearTimeout(clearTimer.current);
    clearTimer.current = window.setTimeout(() => {
      setHighlightedSymbol((current) => (current === symbol ? null : current));
    }, HIGHLIGHT_DURATION_MS);
  }, []);

  return (
    <HighlightContext.Provider value={{ highlightedSymbol, highlightHolding, registerRowRef }}>
      {children}
    </HighlightContext.Provider>
  );
}

export function useHighlight() {
  const ctx = useContext(HighlightContext);
  if (!ctx) throw new Error('useHighlight must be used within a HighlightProvider');
  return ctx;
}
