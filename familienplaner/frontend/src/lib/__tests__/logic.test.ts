import { describe, expect, it } from 'vitest';
import { addMonths, isoWeek, monthGrid, occurrenceDays, startOfWeek, toDateString } from '../dates';
import { bucketByDay, layoutDay } from '../layout';
import { buildRrule, parseRrule } from '../rrule';
import type { EventOccurrence } from '../types';

function occ(partial: Partial<EventOccurrence>): EventOccurrence {
  return {
    id: 1, occurrence_id: '1', calendar_id: 1, title: 'T', description: null, location: null,
    start: '2026-11-24T09:00:00', end: '2026-11-24T10:00:00', all_day: false, timezone: 'Europe/Berlin',
    rrule: null, recurring: false, series_id: null, member_ids: [], color: null, category: null, read_only: false,
    ...partial,
  };
}

describe('dates', () => {
  it('start of week (Monday/Sunday)', () => {
    const sun = new Date(2026, 10, 22);
    expect(toDateString(startOfWeek(sun, 'monday'))).toBe('2026-11-16');
    expect(toDateString(startOfWeek(sun, 'sunday'))).toBe('2026-11-22');
  });
  it('iso week', () => {
    expect(isoWeek(new Date(2026, 10, 23))).toBe(48);
    expect(isoWeek(new Date(2027, 0, 1))).toBe(53);
  });
  it('month grid covers full weeks', () => {
    const grid = monthGrid(new Date(2026, 10, 15), 'monday');
    expect(grid.length % 7).toBe(0);
    expect(toDateString(grid[0])).toBe('2026-10-26');
    expect(toDateString(grid.at(-1)!)).toBe('2026-12-06');
  });
  it('addMonths clamps day', () => {
    expect(toDateString(addMonths(new Date(2026, 0, 31), 1))).toBe('2026-02-28');
  });
  it('occurrence days: all-day end exclusive, timed ending at midnight', () => {
    expect(occurrenceDays(occ({ all_day: true, start: '2026-11-25', end: '2026-11-27' })).map(toDateString))
      .toEqual(['2026-11-25', '2026-11-26']);
    expect(occurrenceDays(occ({ start: '2026-11-25T22:00:00', end: '2026-11-26T00:00:00' })).map(toDateString))
      .toEqual(['2026-11-25']);
  });
});

describe('layout', () => {
  it('buckets multi-day events and sorts all-day first', () => {
    const map = bucketByDay([
      occ({ id: 1, title: 'B', start: '2026-11-24T08:00:00', end: '2026-11-24T09:00:00' }),
      occ({ id: 2, title: 'A', all_day: true, start: '2026-11-24', end: '2026-11-26' }),
    ]);
    expect(map.get('2026-11-24')!.map((e) => e.id)).toEqual([2, 1]);
    expect(map.get('2026-11-25')!.map((e) => e.id)).toEqual([2]);
  });
  it('places overlapping events side by side', () => {
    const day = new Date(2026, 10, 24);
    const res = layoutDay([
      occ({ id: 1, start: '2026-11-24T09:00:00', end: '2026-11-24T10:00:00' }),
      occ({ id: 2, start: '2026-11-24T09:30:00', end: '2026-11-24T11:00:00' }),
      occ({ id: 3, start: '2026-11-24T10:00:00', end: '2026-11-24T10:30:00' }),
      occ({ id: 4, start: '2026-11-24T12:00:00', end: '2026-11-24T13:00:00' }),
    ], day);
    const byId = Object.fromEntries(res.map((p) => [p.occ.id, p]));
    expect([byId[1].column, byId[2].column, byId[3].column]).toEqual([0, 1, 0]);
    expect(byId[1].columns).toBe(2);
    expect(byId[4].columns).toBe(1);
  });
  it('clips events crossing midnight', () => {
    const res = layoutDay([occ({ start: '2026-11-24T23:00:00', end: '2026-11-25T01:00:00' })], new Date(2026, 10, 25));
    expect(res[0].startMin).toBe(0);
    expect(res[0].endMin).toBe(60);
    expect(res[0].continuesBefore).toBe(true);
  });
});

describe('rrule', () => {
  const tue = new Date(2026, 10, 24);
  it('builds and parses presets', () => {
    for (const preset of ['daily', 'weekdays', 'weekly', 'biweekly', 'monthly', 'yearly'] as const) {
      expect(parseRrule(buildRrule(preset, tue)).preset).toBe(preset);
    }
    expect(buildRrule('weekly', tue)).toBe('FREQ=WEEKLY;BYDAY=TU');
  });
  it('keeps until date', () => {
    const rule = buildRrule('weekly', tue, '2027-06-30');
    expect(parseRrule(rule)).toEqual({ preset: 'weekly', until: '2027-06-30' });
  });
  it('unknown rules are custom', () => {
    expect(parseRrule('FREQ=MONTHLY;BYDAY=2TU;COUNT=3').preset).toBe('custom');
  });
});

import { rangeFor } from '../activities';

describe('activities', () => {
  it('weekend range', () => {
    expect(rangeFor('weekend', new Date(2026, 10, 25))).toEqual({ from: '2026-11-28', to: '2026-11-29' }); // Mi
    expect(rangeFor('weekend', new Date(2026, 10, 28))).toEqual({ from: '2026-11-28', to: '2026-11-29' }); // Sa
    expect(rangeFor('weekend', new Date(2026, 10, 29))).toEqual({ from: '2026-11-29', to: '2026-11-29' }); // So
    expect(rangeFor('week', new Date(2026, 10, 25))).toEqual({ from: '2026-11-25', to: '2026-12-01' });
  });
});
