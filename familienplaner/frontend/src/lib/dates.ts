// Datumshilfen. Annahme: Browser und Backend laufen in derselben Zeitzone (der Pi im Haushalt).
import type { EventOccurrence } from './types';

export const DAY_MS = 86_400_000;
const LOCALE = 'de-DE';

export function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n, d.getHours(), d.getMinutes(), d.getSeconds());
}

export function addMonths(d: Date, n: number): Date {
  const target = new Date(d.getFullYear(), d.getMonth() + n, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  return new Date(target.getFullYear(), target.getMonth(), Math.min(d.getDate(), lastDay));
}

export function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function isWeekend(d: Date): boolean {
  return d.getDay() === 0 || d.getDay() === 6;
}

export function startOfWeek(d: Date, weekStartsOn: 'monday' | 'sunday' = 'monday'): Date {
  const first = weekStartsOn === 'monday' ? 1 : 0;
  const diff = (d.getDay() - first + 7) % 7;
  return startOfDay(addDays(d, -diff));
}

/** ISO-8601-Kalenderwoche. */
export function isoWeek(d: Date): number {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return Math.ceil(((t.getTime() - yearStart.getTime()) / DAY_MS + 1) / 7);
}

const pad = (n: number) => String(n).padStart(2, '0');

/** "YYYY-MM-DD" in Ortszeit. */
export function toDateString(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** "HH:MM" in Ortszeit. */
export function toTimeString(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Zeitpunkt ohne Zeitzone ("YYYY-MM-DDTHH:MM:SS") – das Backend interpretiert ihn als Ortszeit. */
export function toLocalIso(d: Date): string {
  return `${toDateString(d)}T${toTimeString(d)}:${pad(d.getSeconds())}`;
}

export function parseDate(value: string): Date {
  const [y, m, d] = value.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function combine(date: string, time: string): Date {
  const [h, min] = time.split(':').map(Number);
  const d = parseDate(date);
  d.setHours(h, min, 0, 0);
  return d;
}

/** Beginn/Ende eines Vorkommens als lokale Date-Objekte (ganztägig: 00:00, Ende exklusiv). */
export function occurrenceRange(occ: EventOccurrence): { start: Date; end: Date } {
  if (occ.all_day) return { start: parseDate(occ.start), end: parseDate(occ.end) };
  return { start: new Date(occ.start), end: new Date(occ.end) };
}

/** Alle lokalen Tage, die ein Vorkommen berührt. */
export function occurrenceDays(occ: EventOccurrence): Date[] {
  const { start, end } = occurrenceRange(occ);
  const last = startOfDay(new Date(end.getTime() - 1));
  const days: Date[] = [];
  for (let d = startOfDay(start); d <= last; d = addDays(d, 1)) days.push(d);
  return days.length ? days : [startOfDay(start)];
}

export const fmt = {
  time: (d: Date) => d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' }),
  weekdayShort: (d: Date) => d.toLocaleDateString(LOCALE, { weekday: 'short' }).replace('.', ''),
  weekdayLong: (d: Date) => d.toLocaleDateString(LOCALE, { weekday: 'long' }),
  dayMonth: (d: Date) => d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'short' }),
  monthYear: (d: Date) => d.toLocaleDateString(LOCALE, { month: 'long', year: 'numeric' }),
  full: (d: Date) => d.toLocaleDateString(LOCALE, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }),
};

export function weekRangeLabel(start: Date): string {
  const end = addDays(start, 6);
  const sameMonth = start.getMonth() === end.getMonth();
  const left = sameMonth ? `${start.getDate()}.` : fmt.dayMonth(start);
  return `KW ${isoWeek(start)} · ${left} – ${fmt.dayMonth(end)} ${end.getFullYear()}`;
}

/** Tage des Monatsrasters (volle Wochen, die den Monat abdecken). */
export function monthGrid(ref: Date, weekStartsOn: 'monday' | 'sunday'): Date[] {
  const first = new Date(ref.getFullYear(), ref.getMonth(), 1);
  const last = new Date(ref.getFullYear(), ref.getMonth() + 1, 0);
  const start = startOfWeek(first, weekStartsOn);
  const days: Date[] = [];
  for (let d = start; d <= last || days.length % 7 !== 0; d = addDays(d, 1)) days.push(d);
  return days;
}
