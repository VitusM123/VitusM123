// Typisierter REST-Client für das Backend.
import type {
  AccountInfo, GoogleConfig,
  AuthStatus, CalendarInfo, DisplayState, EventInput, EventOccurrence, FamilyMember, FamilyTable,
  ServerInfo, SyncStatus, Theme, UserSettings,
} from './types';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown, params?: Record<string, unknown>): Promise<T> {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) value.forEach((v) => url.searchParams.append(key, String(v)));
    else url.searchParams.set(key, String(value));
  }
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch { /* keine JSON-Antwort */ }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  info: () => request<ServerInfo>('GET', '/api/info'),

  // Termine
  events: (start: string, end: string, members?: number[], calendars?: number[]) =>
    request<EventOccurrence[]>('GET', '/api/events', undefined, { start, end, members, calendars }),
  event: (id: number) => request<EventOccurrence>('GET', `/api/events/${id}`),
  createEvent: (data: EventInput) => request<EventOccurrence>('POST', '/api/events', data),
  updateEvent: (id: number, data: EventInput, occurrenceStart?: string) =>
    request<EventOccurrence>('PUT', `/api/events/${id}`, data, { occurrence_start: occurrenceStart }),
  deleteEvent: (id: number, occurrenceStart?: string) =>
    request<void>('DELETE', `/api/events/${id}`, undefined, { occurrence_start: occurrenceStart }),
  familyTable: (start: string, days = 7) => request<FamilyTable>('GET', '/api/family-table', undefined, { start, days }),

  // Kalender & Mitglieder
  calendars: () => request<CalendarInfo[]>('GET', '/api/calendars'),
  updateCalendar: (id: number, data: Partial<CalendarInfo>) => request<CalendarInfo>('PUT', `/api/calendars/${id}`, data),
  createCalendar: (data: { name: string; color?: string | null; default_member_id?: number | null }) =>
    request<CalendarInfo>('POST', '/api/calendars', data),
  deleteCalendar: (id: number) => request<void>('DELETE', `/api/calendars/${id}`),
  members: () => request<FamilyMember[]>('GET', '/api/members'),
  createMember: (data: Pick<FamilyMember, 'name' | 'color'> & { avatar?: string | null }) =>
    request<FamilyMember>('POST', '/api/members', data),
  updateMember: (id: number, data: Partial<FamilyMember>) => request<FamilyMember>('PUT', `/api/members/${id}`, data),
  deleteMember: (id: number) => request<void>('DELETE', `/api/members/${id}`),
  reorderMembers: (ids: number[]) => request<FamilyMember[]>('PUT', '/api/members/order', ids),

  // Einstellungen & Themes
  themes: () => request<Theme[]>('GET', '/api/themes'),
  activeTheme: () => request<Theme>('GET', '/api/themes/active'),
  selectTheme: (theme: string) => request<UserSettings>('PUT', '/api/settings/theme', { theme }),
  settings: () => request<UserSettings>('GET', '/api/settings'),
  updateSettings: (data: Partial<UserSettings>) => request<UserSettings>('PUT', '/api/settings', data),

  // Display & Sync
  display: () => request<DisplayState>('GET', '/api/display'),
  setDisplay: (data: Partial<Pick<DisplayState, 'screen_on' | 'brightness'>>) =>
    request<DisplayState>('PUT', '/api/display', data),
  wake: () => request<DisplayState>('POST', '/api/display/wake'),
  syncStatus: () => request<SyncStatus>('GET', '/api/sync'),
  sync: () => request<SyncStatus>('POST', '/api/sync'),

  // Konten (Google/iCloud)
  accounts: () => request<AccountInfo[]>('GET', '/api/accounts'),
  deleteAccount: (id: number) => request<void>('DELETE', `/api/accounts/${id}`),
  syncAccount: (id: number) => request<SyncStatus>('POST', `/api/accounts/${id}/sync`),
  googleConfig: () => request<GoogleConfig>('GET', '/api/accounts/google/config'),
  setGoogleConfig: (client_id: string, client_secret: string) =>
    request<GoogleConfig>('PUT', '/api/accounts/google/config', { client_id, client_secret }),
  googleStart: () => request<{ auth_url: string; redirect_uri: string }>('POST', '/api/accounts/google/start'),
  googleComplete: (url: string) => request<AccountInfo>('POST', '/api/accounts/google/complete', { url }),

  // Admin-PIN
  authStatus: () => request<AuthStatus>('GET', '/api/auth/status'),
  setupPin: (pin: string) => request<AuthStatus>('POST', '/api/auth/setup', { pin }),
  login: (pin: string) => request<AuthStatus>('POST', '/api/auth/login', { pin }),
  logout: () => request<AuthStatus>('POST', '/api/auth/logout'),
  changePin: (current_pin: string, new_pin: string) =>
    request<AuthStatus>('POST', '/api/auth/change-pin', { current_pin, new_pin }),
};
