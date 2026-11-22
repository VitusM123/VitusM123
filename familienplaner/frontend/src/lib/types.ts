// Gespiegelte Backend-Schemas (später ggf. aus OpenAPI generieren)

export type ViewId = 'month' | 'week' | 'family' | 'activities' | 'settings' | 'eink';

export interface FamilyMember {
  id: number;
  name: string;
  color: string;
  avatar?: string;
  sortOrder: number;
}

export interface CalendarInfo {
  id: number;
  name: string;
  provider: 'google' | 'icloud' | 'local';
  color?: string;
  readOnly: boolean;
  visible: boolean;
  defaultMemberId?: number;
}

export interface CalendarEvent {
  id: number;
  calendarId: number;
  title: string;
  start: string; // ISO 8601
  end: string;
  allDay: boolean;
  location?: string;
  description?: string;
  memberIds: number[];
  category?: string;
}

export type ActivityCategory =
  | 'open_day' | 'fair' | 'exhibition' | 'market' | 'festival'
  | 'concert' | 'theater' | 'sports' | 'kids' | 'workshop' | 'other';

export interface Activity {
  id: number;
  title: string;
  category: ActivityCategory;
  start: string;
  end?: string;
  venue?: string;
  address?: string;
  distanceKm?: number;
  url?: string;
  imageUrl?: string;
  source: string;
}

export interface ActivitySearch {
  lat?: number;
  lon?: number;
  address?: string;
  radiusKm: number;
  dateFrom: string;
  dateTo: string;
  categories: ActivityCategory[];
  keywords?: string[];
}

export interface Theme {
  id: string;
  name: string;
  mode: 'light' | 'dark' | 'eink';
  tokens: Record<string, string>;
  memberPalette: string[];
  font?: { family: string; scale: number };
}
