// Spiegel der Backend-Schemas (app/schemas.py). Feldnamen wie in der API (snake_case).

export type ViewId = 'month' | 'week' | 'family' | 'activities' | 'settings' | 'eink';
export type CalendarViewName = 'month' | 'week' | 'family';

export interface FamilyMember {
  id: number;
  name: string;
  color: string;
  avatar: string | null;
  sort_order: number;
}

export interface CalendarInfo {
  id: number;
  account_id: number;
  provider: 'google' | 'icloud' | 'local';
  name: string;
  color: string | null;
  read_only: boolean;
  visible: boolean;
  is_default: boolean;
  /** Personen, denen der Kalender gehört (gilt für Termine ohne eigene Personenauswahl) */
  member_ids: number[];
}

/** Ein konkretes Vorkommen. Ganztägig: start/end = "YYYY-MM-DD" (end exklusiv), sonst ISO-UTC. */
export interface EventOccurrence {
  id: number;
  occurrence_id: string;
  calendar_id: number;
  title: string;
  description: string | null;
  location: string | null;
  start: string;
  end: string;
  all_day: boolean;
  timezone: string;
  rrule: string | null;
  recurring: boolean;
  /** id der Serie (bei Serien = eigene id, bei Einzeländerungen = Master), sonst null */
  series_id: number | null;
  member_ids: number[];
  color: string | null;
  category: string | null;
  read_only: boolean;
}

export interface EventInput {
  calendar_id?: number | null;
  title?: string;
  start?: string;
  end?: string | null;
  all_day?: boolean;
  timezone?: string | null;
  description?: string | null;
  location?: string | null;
  rrule?: string | null;
  member_ids?: number[];
  category?: string | null;
}

export interface FamilyDay {
  date: string;
  cells: Record<string, EventOccurrence[]>;
  unassigned: EventOccurrence[];
}

export interface FamilyTable {
  members: FamilyMember[];
  days: FamilyDay[];
}

export interface NightMode {
  enabled: boolean;
  off: string;
  on: string;
}

export interface UserSettings {
  theme: string;
  auto_theme: boolean;
  day_theme: string;
  night_theme: string;
  day_starts: string;
  night_starts: string;
  default_view: CalendarViewName;
  week_starts_on: 'monday' | 'sunday';
  night_mode: NightMode;
  home: { address: string; lat: number | null; lon: number | null };
  activity_radius_km: number;
}

export type ActivityCategory =
  | 'open_day' | 'fair' | 'exhibition' | 'market' | 'festival'
  | 'concert' | 'theater' | 'sports' | 'kids' | 'workshop' | 'other';

export interface Activity {
  id: number;
  title: string;
  description: string | null;
  category: ActivityCategory;
  /** ganztägig: "YYYY-MM-DD", sonst ISO-UTC */
  start: string;
  end: string | null;
  all_day: boolean;
  venue: string | null;
  address: string | null;
  lat: number | null;
  lon: number | null;
  distance_km: number | null;
  url: string | null;
  image_url: string | null;
  source: string;
  event_id: number | null;
}

export interface ActivitySearch {
  address?: string | null;
  lat?: number | null;
  lon?: number | null;
  radius_km: number;
  date_from: string;
  date_to: string;
  categories: ActivityCategory[];
  query?: string | null;
  include_unlocated?: boolean;
}

export interface ActivitySearchResult {
  center: { lat: number; lon: number; label: string };
  results: Activity[];
  total_in_db: number;
}

export type ActivitySourceType = 'ical' | 'rss' | 'ticketmaster' | 'scraper';

export interface ActivitySourceInfo {
  id: number;
  type: ActivitySourceType;
  name: string;
  config: Record<string, string>;
  enabled: boolean;
  last_fetch: string | null;
  last_error: string | null;
  last_count: number;
}

export interface Theme {
  id: string;
  name: string;
  mode: 'light' | 'dark' | 'eink';
  tokens: Record<string, string>;
  memberPalette: string[];
  font: { family: string; scale: number };
  builtin: boolean;
}

export interface DisplayState {
  screen_on: boolean;
  brightness: number;
  night_active: boolean;
  hardware_backlight: boolean;
}

export interface SyncStatus {
  state: 'idle' | 'running' | 'error';
  last_run: string | null;
  last_error: string | null;
  accounts_synced: number;
}

export interface AccountInfo {
  id: number;
  provider: 'google' | 'icloud' | 'local';
  display_name: string;
  last_sync: string | null;
  last_error: string | null;
  calendar_count: number;
}

export interface GoogleConfig {
  configured: boolean;
  source: 'config' | 'settings' | null;
  client_id: string | null;
  redirect_uri: string;
}

export interface AuthStatus {
  pin_set: boolean;
  authenticated: boolean;
}

export interface ServerInfo {
  version: string;
  timezone: string;
  language: string;
  display_mode: 'lcd' | 'eink';
}

export type ServerEventType =
  | 'events.changed' | 'calendars.changed' | 'members.changed' | 'sync.status'
  | 'theme.changed' | 'settings.changed' | 'display.changed' | 'activities.changed';

export interface ServerEvent {
  type: ServerEventType;
  payload: Record<string, unknown>;
}
