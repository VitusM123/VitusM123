// Layout-Berechnungen für die Kalenderansichten.
import { addDays, occurrenceDays, occurrenceRange, startOfDay, toDateString } from './dates';
import type { EventOccurrence } from './types';

/** Vorkommen nach lokalem Tag gruppieren ("YYYY-MM-DD" → Liste), mehrtägige an jedem Tag. */
export function bucketByDay(events: EventOccurrence[]): Map<string, EventOccurrence[]> {
  const map = new Map<string, EventOccurrence[]>();
  for (const occ of events) {
    for (const day of occurrenceDays(occ)) {
      const key = toDateString(day);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(occ);
    }
  }
  for (const list of map.values()) list.sort(compareOccurrences);
  return map;
}

export function compareOccurrences(a: EventOccurrence, b: EventOccurrence): number {
  if (a.all_day !== b.all_day) return a.all_day ? -1 : 1;
  const sa = occurrenceRange(a).start.getTime();
  const sb = occurrenceRange(b).start.getTime();
  return sa - sb || a.title.localeCompare(b.title);
}

export interface PositionedEvent {
  occ: EventOccurrence;
  /** Minuten ab 00:00 des Tages (auf den Tag beschnitten) */
  startMin: number;
  endMin: number;
  column: number;
  columns: number;
  continuesBefore: boolean;
  continuesAfter: boolean;
}

/**
 * Zeitgebundene Termine eines Tages so anordnen, dass sich überlappende nebeneinander stehen.
 * Überlappende Termine bilden Cluster, jeder Termin erhält die erste freie Spalte im Cluster.
 */
export function layoutDay(events: EventOccurrence[], day: Date, minDuration = 20): PositionedEvent[] {
  const dayStart = startOfDay(day).getTime();
  const dayEnd = addDays(startOfDay(day), 1).getTime();
  const items = events
    .filter((e) => !e.all_day)
    .map((occ) => {
      const { start, end } = occurrenceRange(occ);
      const s = Math.max(start.getTime(), dayStart);
      const e = Math.min(end.getTime(), dayEnd);
      const startMin = (s - dayStart) / 60_000;
      return {
        occ,
        startMin,
        endMin: Math.max((e - dayStart) / 60_000, startMin + minDuration),
        column: 0,
        columns: 1,
        continuesBefore: start.getTime() < dayStart,
        continuesAfter: end.getTime() > dayEnd,
      };
    })
    .filter((p) => p.endMin > 0 && p.startMin < 1440)
    .sort((a, b) => a.startMin - b.startMin || b.endMin - a.endMin);

  let cluster: PositionedEvent[] = [];
  let columnsEnd: number[] = [];
  let clusterEnd = -1;
  const flush = () => {
    const n = columnsEnd.length;
    for (const p of cluster) p.columns = n;
    cluster = [];
    columnsEnd = [];
  };
  for (const item of items) {
    if (item.startMin >= clusterEnd) flush();
    let col = columnsEnd.findIndex((end) => end <= item.startMin);
    if (col === -1) {
      col = columnsEnd.length;
      columnsEnd.push(item.endMin);
    } else {
      columnsEnd[col] = item.endMin;
    }
    item.column = col;
    cluster.push(item);
    clusterEnd = Math.max(clusterEnd, item.endMin);
  }
  flush();
  return items;
}

/** Farbe eines Termins: Farbe der Person (bei genau einer), sonst Kalenderfarbe, sonst Akzent. */
export function eventColor(occ: EventOccurrence, memberColor: (id: number) => string | undefined): string {
  if (occ.member_ids.length === 1) {
    const c = memberColor(occ.member_ids[0]);
    if (c) return c;
  }
  return occ.color ?? 'var(--color-accent)';
}
