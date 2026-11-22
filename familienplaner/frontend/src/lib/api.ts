// Typisierter REST-Client für /api/*. TODO: Implementierung
import type { Activity, ActivitySearch, CalendarEvent, CalendarInfo, FamilyMember, Theme } from './types';

export interface Api {
  events(from: string, to: string, memberIds?: number[]): Promise<CalendarEvent[]>;
  calendars(): Promise<CalendarInfo[]>;
  members(): Promise<FamilyMember[]>;
  searchActivities(q: ActivitySearch): Promise<Activity[]>;
  addActivityToCalendar(activityId: number, calendarId: number, memberIds: number[]): Promise<CalendarEvent>;
  themes(): Promise<Theme[]>;
}
