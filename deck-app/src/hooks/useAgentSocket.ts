// Task 29 — owns the /ws/agent WebSocket connection (task 28c). One
// connection per mount, reused across turns; task 28c's --resume-based
// session_id continuity happens entirely server-side, this hook just
// relays raw events. The composer is expected to disable itself while a
// turn is pending — the server processes one prompt fully (a full
// run_one_shot call) before reading the next message off the socket, so
// overlapping turns would scramble which events belong to which turn.
import { useCallback, useEffect, useRef, useState } from 'react';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AgentEvent = Record<string, any>;

export interface AgentTurn {
  id: string;
  prompt: string;
  events: AgentEvent[];
  status: 'pending' | 'done' | 'error';
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
const WS_URL = BASE_URL.replace(/^http/, 'ws') + '/ws/agent';

export function useAgentSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const currentTurnId = useRef<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [turns, setTurns] = useState<AgentTurn[]>([]);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    ws.onmessage = (rawEvent) => {
      let event: AgentEvent;
      try {
        event = JSON.parse(rawEvent.data);
      } catch {
        return;
      }
      const id = currentTurnId.current;
      if (!id) return;

      const isTerminal = event.type === 'result' || event.type === 'error';
      setTurns((prev) =>
        prev.map((t) =>
          t.id === id
            ? {
                ...t,
                events: [...t.events, event],
                status: isTerminal ? (event.type === 'error' ? 'error' : 'done') : t.status,
              }
            : t,
        ),
      );
      if (isTerminal) currentTurnId.current = null;
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, []);

  const sendPrompt = useCallback((prompt: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const id = crypto.randomUUID();
    currentTurnId.current = id;
    setTurns((prev) => [...prev, { id, prompt, events: [], status: 'pending' }]);
    wsRef.current.send(JSON.stringify({ prompt }));
  }, []);

  const isTurnPending = turns.length > 0 && turns[turns.length - 1].status === 'pending';

  return { connected, turns, sendPrompt, isTurnPending };
}
