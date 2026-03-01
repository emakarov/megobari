import { useEffect, useRef, useState, useCallback } from "react";
import type { Message } from "@/lib/api";

/**
 * WebSocket hook that streams new messages in real-time.
 * Prepends new messages to `initialMessages` (newest first).
 */
export function useLiveMessages(initialMessages: Message[]) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Sync when initial data changes (e.g. React Query refetch)
  useEffect(() => {
    setMessages((prev) => {
      // Merge: keep any WS-delivered messages that aren't in the new batch
      const initialIds = new Set(initialMessages.map((m) => m.id));
      const wsOnly = prev.filter((m) => !initialIds.has(m.id));
      // Sort newest first by timestamp, then by id as tiebreaker
      return [...wsOnly, ...initialMessages].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime() ||
          b.id - a.id
      );
    });
  }, [initialMessages]);

  const connect = useCallback(() => {
    const token = localStorage.getItem("dashboard_token") || "";
    if (!token) return;

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}/api/ws/messages?token=${encodeURIComponent(token)}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const msg: Message = JSON.parse(ev.data);
        setMessages((prev) => {
          // Deduplicate by id
          if (prev.some((m) => m.id === msg.id)) return prev;
          // Prepend (newest first), cap at 50
          return [msg, ...prev].slice(0, 50);
        });
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      // Reconnect after 3s
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return messages;
}
