// WebSocket-Client für Live-Updates: events.changed, sync.status, theme.changed
export type ServerEvent = { type: string; payload?: unknown };
// TODO: connect(), automatisches Reconnect, Dispatch an Stores
