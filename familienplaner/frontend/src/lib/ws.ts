// WebSocket-Client mit automatischem Wiederverbinden und Keepalive.
import type { ServerEvent } from './types';

type Listener = (event: ServerEvent) => void;
type StatusListener = (connected: boolean) => void;

export function connectEvents(onEvent: Listener, onStatus?: StatusListener): () => void {
  let socket: WebSocket | null = null;
  let retry = 0;
  let closed = false;
  let keepalive: ReturnType<typeof setInterval> | undefined;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(`${proto}://${window.location.host}/ws`);
    socket.onopen = () => {
      retry = 0;
      onStatus?.(true);
      keepalive = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send('ping'), 30_000);
    };
    socket.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data) as ServerEvent);
      } catch { /* ungültige Nachricht ignorieren */ }
    };
    socket.onclose = () => {
      clearInterval(keepalive);
      onStatus?.(false);
      if (closed) return;
      const delay = Math.min(30_000, 1000 * 2 ** retry++);   // 1 s, 2 s, 4 s … max. 30 s
      reconnectTimer = setTimeout(open, delay);
    };
  };

  open();
  return () => {
    closed = true;
    clearTimeout(reconnectTimer);
    clearInterval(keepalive);
    socket?.close();
  };
}
