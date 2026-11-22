// Vorlagen für Wiederholungen (Teilmenge von RFC 5545, ausreichend für Familientermine).

export type RepeatPreset = 'none' | 'daily' | 'weekdays' | 'weekly' | 'biweekly' | 'monthly' | 'yearly' | 'custom';

const BYDAY = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];

export const REPEAT_LABELS: Record<RepeatPreset, string> = {
  none: 'Keine',
  daily: 'Täglich',
  weekdays: 'Werktags (Mo–Fr)',
  weekly: 'Wöchentlich',
  biweekly: 'Alle 2 Wochen',
  monthly: 'Monatlich',
  yearly: 'Jährlich',
  custom: 'Benutzerdefiniert',
};

export function buildRrule(preset: RepeatPreset, start: Date, until?: string | null, custom?: string | null): string | null {
  let rule: string | null;
  switch (preset) {
    case 'none': return null;
    case 'daily': rule = 'FREQ=DAILY'; break;
    case 'weekdays': rule = 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR'; break;
    case 'weekly': rule = `FREQ=WEEKLY;BYDAY=${BYDAY[start.getDay()]}`; break;
    case 'biweekly': rule = `FREQ=WEEKLY;INTERVAL=2;BYDAY=${BYDAY[start.getDay()]}`; break;
    case 'monthly': rule = `FREQ=MONTHLY;BYMONTHDAY=${start.getDate()}`; break;
    case 'yearly': rule = 'FREQ=YEARLY'; break;
    case 'custom': return custom ?? null;
  }
  if (until) rule += `;UNTIL=${until.replaceAll('-', '')}T235959Z`;
  return rule;
}

/** Erkennt eine Vorlage in einer bestehenden Regel (UNTIL wird separat zurückgegeben). */
export function parseRrule(rule: string | null): { preset: RepeatPreset; until: string | null } {
  if (!rule) return { preset: 'none', until: null };
  const parts = Object.fromEntries(
    rule.replace(/^RRULE:/i, '').split(';').map((p) => p.split('=') as [string, string]),
  );
  const until = parts.UNTIL ? `${parts.UNTIL.slice(0, 4)}-${parts.UNTIL.slice(4, 6)}-${parts.UNTIL.slice(6, 8)}` : null;
  const known = new Set(['FREQ', 'INTERVAL', 'BYDAY', 'BYMONTHDAY', 'UNTIL']);
  if (Object.keys(parts).some((k) => !known.has(k)) || parts.COUNT) return { preset: 'custom', until: null };
  const interval = parts.INTERVAL ?? '1';
  const days = parts.BYDAY?.split(',') ?? [];
  switch (parts.FREQ) {
    case 'DAILY': return interval === '1' && !days.length ? { preset: 'daily', until } : { preset: 'custom', until: null };
    case 'WEEKLY':
      if (days.join(',') === 'MO,TU,WE,TH,FR' && interval === '1') return { preset: 'weekdays', until };
      if (days.length <= 1 && interval === '1') return { preset: 'weekly', until };
      if (days.length <= 1 && interval === '2') return { preset: 'biweekly', until };
      return { preset: 'custom', until: null };
    case 'MONTHLY': return interval === '1' ? { preset: 'monthly', until } : { preset: 'custom', until: null };
    case 'YEARLY': return interval === '1' ? { preset: 'yearly', until } : { preset: 'custom', until: null };
  }
  return { preset: 'custom', until: null };
}

export function describeRrule(rule: string | null): string {
  const { preset, until } = parseRrule(rule);
  const base = REPEAT_LABELS[preset];
  return until ? `${base} bis ${until.split('-').reverse().join('.')}` : base;
}
