// Beschriftungen und Zeiträume für die Aktivitätensuche.
import { addDays, startOfDay, toDateString } from './dates';
import type { ActivityCategory } from './types';

export const CATEGORIES: { id: ActivityCategory; label: string; icon: string }[] = [
  { id: 'open_day', label: 'Tag der offenen Tür', icon: '🚪' },
  { id: 'fair', label: 'Messe', icon: '🏛️' },
  { id: 'exhibition', label: 'Ausstellung', icon: '🖼️' },
  { id: 'market', label: 'Markt', icon: '🛍️' },
  { id: 'festival', label: 'Fest', icon: '🎪' },
  { id: 'kids', label: 'Kinder', icon: '🧸' },
  { id: 'concert', label: 'Konzert', icon: '🎵' },
  { id: 'theater', label: 'Theater', icon: '🎭' },
  { id: 'sports', label: 'Sport', icon: '⚽' },
  { id: 'workshop', label: 'Workshop', icon: '✂️' },
  { id: 'other', label: 'Sonstiges', icon: '✦' },
];

export const categoryInfo = (id: ActivityCategory) => CATEGORIES.find((c) => c.id === id) ?? CATEGORIES.at(-1)!;

export type RangePreset = 'weekend' | 'week' | 'month';

export const RANGE_LABELS: Record<RangePreset, string> = {
  weekend: 'Dieses Wochenende',
  week: 'Nächste 7 Tage',
  month: 'Nächste 30 Tage',
};

/** Zeitraum (inklusive) für eine Vorlage. Wochenende: kommender Sa–So, am Wochenende das laufende. */
export function rangeFor(preset: RangePreset, today = new Date()): { from: string; to: string } {
  const t = startOfDay(today);
  if (preset === 'weekend') {
    const dow = t.getDay();                  // 0 = So, 6 = Sa
    const sat = dow === 0 ? addDays(t, -1) : addDays(t, (6 - dow + 7) % 7);
    const from = dow === 0 || dow === 6 ? t : sat;
    return { from: toDateString(from), to: toDateString(addDays(sat, 1)) };
  }
  return { from: toDateString(t), to: toDateString(addDays(t, preset === 'week' ? 6 : 29)) };
}
