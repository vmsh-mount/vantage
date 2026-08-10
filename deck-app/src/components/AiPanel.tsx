// Task 29 — the ask-your-portfolio panel (planning-phase2.md §5.3). The
// four elements the plan names by name: composer, reasoning blocks, tool
// cards, UI-actions. Mounted once in Layout (sibling to Outlet) so the WS
// connection and transcript persist across page navigation — a real side
// panel, not a per-page widget.
import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAgentSocket, type AgentEvent, type AgentTurn } from '../hooks/useAgentSocket';
import { useHighlight } from '../lib/highlight';

const UI_ACTION_HIGHLIGHT = 'mcp__vantage__highlight_holding';

type RenderItem =
  | { kind: 'thinking'; text: string }
  | { kind: 'text'; text: string }
  | { kind: 'tool'; id: string; name: string; input: Record<string, unknown>; result?: string; isError?: boolean }
  | { kind: 'ui-action'; id: string; input: Record<string, unknown>; result?: string; isError?: boolean }
  | { kind: 'error'; message: string };

function toolLabel(name: string): string {
  return name.startsWith('mcp__vantage__') ? name.slice('mcp__vantage__'.length) : name;
}

function resultPreview(content: unknown): string {
  const text = typeof content === 'string' ? content : JSON.stringify(content);
  return text.length > 400 ? text.slice(0, 400) + '…' : text;
}

// Every tool_use — including the UI-action one — is correlated with its
// real tool_result here. Deliberately not special-cased into "fire and
// forget": whether the highlight actually happened depends on whether the
// permission system actually allowed the call, same as any other tool, and
// the UI should only claim it happened once the result confirms it did (a
// real bug this task's own browser verification caught: the panel first
// rendered "Highlighted GAIL" from the tool_use alone, while the matching
// tool_result showed the call had actually been denied).
function buildTurnItems(turn: AgentTurn): RenderItem[] {
  const items: RenderItem[] = [];
  const indexByToolUseId = new Map<string, number>();

  for (const event of turn.events as AgentEvent[]) {
    if (event.type === 'assistant') {
      for (const block of event.message?.content ?? []) {
        if (block.type === 'thinking' && block.thinking) {
          items.push({ kind: 'thinking', text: block.thinking });
        } else if (block.type === 'text' && block.text) {
          items.push({ kind: 'text', text: block.text });
        } else if (block.type === 'tool_use') {
          indexByToolUseId.set(block.id, items.length);
          items.push(
            block.name === UI_ACTION_HIGHLIGHT
              ? { kind: 'ui-action', id: block.id, input: block.input ?? {} }
              : { kind: 'tool', id: block.id, name: block.name, input: block.input ?? {} },
          );
        }
      }
    } else if (event.type === 'user') {
      for (const block of event.message?.content ?? []) {
        if (block.type === 'tool_result') {
          const idx = indexByToolUseId.get(block.tool_use_id);
          const item = idx !== undefined ? items[idx] : undefined;
          if (item?.kind === 'tool' || item?.kind === 'ui-action') {
            item.result = resultPreview(block.content);
            item.isError = Boolean(block.is_error);
          }
        }
      }
    } else if (event.type === 'error') {
      items.push({ kind: 'error', message: String(event.message ?? 'Something went wrong.') });
    }
  }
  return items;
}

function TurnView({ turn }: { turn: AgentTurn }) {
  const items = buildTurnItems(turn);
  return (
    <div className="ai-turn">
      <div className="ai-bubble ai-bubble-user">{turn.prompt}</div>
      {items.map((item, i) => {
        if (item.kind === 'thinking') {
          return (
            <details key={i} className="ai-reasoning">
              <summary>Reasoning</summary>
              <p>{item.text}</p>
            </details>
          );
        }
        if (item.kind === 'text') {
          return (
            <div key={i} className="ai-bubble ai-bubble-assistant ai-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
            </div>
          );
        }
        if (item.kind === 'tool') {
          return (
            <details key={i} className={`ai-tool-card${item.isError ? ' ai-tool-error' : ''}`}>
              <summary>
                <span className="ai-tool-name">{toolLabel(item.name)}</span>
                {Object.keys(item.input).length > 0 && (
                  <span className="ai-tool-args">{JSON.stringify(item.input)}</span>
                )}
              </summary>
              <pre>{item.result ?? '…'}</pre>
            </details>
          );
        }
        if (item.kind === 'ui-action') {
          const symbol = String(item.input.symbol ?? '');
          if (item.result === undefined) {
            return (
              <div key={i} className="ai-action-note">
                → Highlighting <strong>{symbol}</strong>…
              </div>
            );
          }
          if (item.isError) {
            return (
              <div key={i} className="ai-action-note ai-action-denied">
                ⚠ Could not highlight <strong>{symbol}</strong> — denied by permission settings
              </div>
            );
          }
          return (
            <div key={i} className="ai-action-note">
              → Highlighted <strong>{symbol}</strong> on the Dashboard
            </div>
          );
        }
        return (
          <p key={i} className="error-state">
            {item.message}
          </p>
        );
      })}
      {turn.status === 'pending' && <div className="ai-thinking-dots">···</div>}
    </div>
  );
}

export function AiPanel() {
  const { connected, turns, sendPrompt, isTurnPending } = useAgentSocket();
  const { highlightHolding } = useHighlight();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const triggeredHighlights = useRef<Set<string>>(new Set());

  // Only acts once the real tool_result confirms the call actually
  // succeeded — see buildTurnItems's comment for the bug this avoids.
  useEffect(() => {
    for (const turn of turns) {
      for (const item of buildTurnItems(turn)) {
        if (item.kind !== 'ui-action' || item.isError || item.result === undefined) continue;
        if (triggeredHighlights.current.has(item.id)) continue;
        triggeredHighlights.current.add(item.id);
        const symbol = item.input.symbol;
        if (symbol) highlightHolding(String(symbol));
      }
    }
  }, [turns, highlightHolding]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns]);

  function submit() {
    const prompt = draft.trim();
    if (!prompt || isTurnPending || !connected) return;
    sendPrompt(prompt);
    setDraft('');
  }

  return (
    <>
      {/* Only floats bottom-right while closed — while open, the close
          control lives in the panel header instead, so it never overlaps
          the composer's own Send button in the same corner (a real bug
          caught in browser verification, not a hypothetical). */}
      {!open && (
        <button className="ai-fab" onClick={() => setOpen(true)} aria-label="Ask your portfolio">
          💬
        </button>
      )}
      <aside className={`ai-panel${open ? ' ai-panel-open' : ''}`}>
        <div className="ai-panel-header">
          <p className="ai-panel-title">Ask Vantage</p>
          <div className="ai-panel-header-right">
            <span className={`ai-status-dot ${connected ? 'ai-status-connected' : 'ai-status-disconnected'}`} />
            <button className="ai-panel-close" onClick={() => setOpen(false)} aria-label="Close portfolio assistant">
              ×
            </button>
          </div>
        </div>
        <div className="ai-panel-body" ref={scrollRef}>
          {turns.length === 0 && (
            <p className="ai-panel-empty">
              Ask about your portfolio — net worth, risk, tax opportunities, or a specific holding.
              Every number comes from a real tool call, shown below the answer.
            </p>
          )}
          {turns.map((turn) => (
            <TurnView key={turn.id} turn={turn} />
          ))}
        </div>
        <div className="ai-composer">
          <textarea
            placeholder={connected ? 'Ask about your portfolio…' : 'Connecting…'}
            value={draft}
            disabled={!connected || isTurnPending}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <button
            className="btn btn-primary btn-sm"
            disabled={!connected || isTurnPending || !draft.trim()}
            onClick={submit}
          >
            {isTurnPending ? '…' : 'Send'}
          </button>
        </div>
      </aside>
    </>
  );
}
