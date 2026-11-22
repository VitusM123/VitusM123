<script lang="ts">
  import { untrack } from 'svelte';
  import { api, ApiError } from '../lib/api';
  import { app } from '../lib/app.svelte';
  import { addDays, combine, occurrenceRange, parseDate, toDateString, toLocalIso, toTimeString } from '../lib/dates';
  import { editor } from '../lib/editor.svelte';
  import { buildRrule, describeRrule, parseRrule, REPEAT_LABELS, type RepeatPreset } from '../lib/rrule';
  import type { EventInput, EventOccurrence } from '../lib/types';
  import Modal from './Modal.svelte';

  type Scope = 'single' | 'series';
  type Pending = { action: 'save' | 'delete' } | null;

  // --- Formularzustand ------------------------------------------------------------------------
  let title = $state('');
  let allDay = $state(false);
  let startDate = $state('');
  let startTime = $state('09:00');
  let endDate = $state('');           // inklusiv angezeigt (auch bei ganztägig)
  let endTime = $state('10:00');
  let memberIds = $state<number[]>([]);
  let calendarId = $state<number | null>(null);
  let repeat = $state<RepeatPreset>('none');
  let until = $state('');
  let location = $state('');
  let description = $state('');
  let error = $state<string | null>(null);
  let busy = $state(false);
  let pending = $state<Pending>(null);
  let confirmDelete = $state(false);

  const occ = $derived(editor.occurrence);
  const isNew = $derived(occ === null);
  const readOnly = $derived(occ?.read_only ?? false);
  /** Vorkommen einer Serie (Master) */
  const isSeriesOccurrence = $derived(!!occ && !!occ.rrule);
  /** Einzeln geändertes Vorkommen einer Serie */
  const isOverride = $derived(!!occ && occ.recurring && !occ.rrule && occ.series_id !== null);
  const originalRule = $derived(occ?.rrule ?? null);

  // Formular bei jedem Öffnen neu befüllen
  $effect(() => {
    void editor.session;
    if (!untrack(() => editor.open)) return;
    init(untrack(() => editor.occurrence));
  });

  function init(o: EventOccurrence | null) {
    lastStart = null;
    error = null;
    pending = null;
    confirmDelete = false;
    if (o) {
      const { start, end } = occurrenceRange(o);
      title = o.title;
      allDay = o.all_day;
      startDate = toDateString(start);
      startTime = toTimeString(start);
      endDate = toDateString(o.all_day ? addDays(end, -1) : end);
      endTime = toTimeString(end);
      memberIds = [...o.member_ids];
      calendarId = o.calendar_id;
      const parsed = parseRrule(o.rrule);
      repeat = parsed.preset;
      until = parsed.until ?? '';
      location = o.location ?? '';
      description = o.description ?? '';
    } else {
      const d = editor.defaults!;
      title = '';
      allDay = d.allDay;
      startDate = toDateString(d.start);
      startTime = toTimeString(d.start);
      endDate = toDateString(d.allDay ? addDays(d.end, -1) : d.end);
      endTime = toTimeString(d.end);
      memberIds = [...d.memberIds];
      calendarId = (app.calendars.find((c) => c.is_default && !c.read_only) ?? app.writableCalendars[0])?.id ?? null;
      repeat = 'none';
      until = '';
      location = '';
      description = '';
    }
  }

  // Beim Verschieben des Beginns das Ende mitziehen (Dauer bleibt erhalten)
  let lastStart: { date: string; time: string } | null = null;   // bewusst nicht reaktiv
  $effect(() => {
    const cur = { date: startDate, time: startTime };
    const prev = lastStart;
    lastStart = cur;
    if (!prev || !prev.date || !cur.date || (prev.date === cur.date && prev.time === cur.time)) return;
    untrack(() => {
      if (!endDate) return;
      const oldStart = allDay ? parseDate(prev.date) : combine(prev.date, prev.time);
      const newStart = allDay ? parseDate(cur.date) : combine(cur.date, cur.time);
      const oldEnd = allDay ? parseDate(endDate) : combine(endDate, endTime);
      const shifted = new Date(oldEnd.getTime() + (newStart.getTime() - oldStart.getTime()));
      endDate = toDateString(shifted);
      if (!allDay) endTime = toTimeString(shifted);
    });
  });

  function toggleMember(id: number) {
    memberIds = memberIds.includes(id) ? memberIds.filter((m) => m !== id) : [...memberIds, id];
  }

  /** Eingaben prüfen und in Start/Ende umrechnen. */
  function times(): { start: Date; end: Date } | null {
    if (!startDate || !endDate) return fail('Bitte Datum angeben');
    if (allDay) {
      const start = parseDate(startDate);
      const end = addDays(parseDate(endDate), 1);
      if (end <= start) return fail('Das Ende darf nicht vor dem Beginn liegen');
      return { start, end };
    }
    const start = combine(startDate, startTime);
    const end = combine(endDate, endTime);
    if (end <= start) return fail('Das Ende muss nach dem Beginn liegen');
    return { start, end };
  }

  function fail(message: string): null {
    error = message;
    return null;
  }

  function payload(start: Date, end: Date, withRule: boolean): EventInput {
    const data: EventInput = {
      title: title.trim(),
      all_day: allDay,
      start: allDay ? toDateString(start) : toLocalIso(start),
      end: allDay ? toDateString(end) : toLocalIso(end),
      member_ids: memberIds,
      location: location.trim() || null,
      description: description.trim() || null,
    };
    if (withRule) data.rrule = buildRrule(repeat, start, until || null, originalRule);
    return data;
  }

  async function run(fn: () => Promise<unknown>, success: string) {
    busy = true;
    error = null;
    try {
      await fn();
      app.notify(success);
      editor.close();
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen';
      pending = null;
    } finally {
      busy = false;
    }
  }

  function save() {
    if (!title.trim()) return void fail('Bitte einen Titel eingeben');
    if (!times()) return;
    if (isSeriesOccurrence || isOverride) {
      pending = { action: 'save' };
      return;
    }
    void doSave('series');
  }

  async function doSave(scope: Scope) {
    const t = times();
    if (!t) return;
    pending = null;
    if (isNew) {
      return run(() => api.createEvent({ ...payload(t.start, t.end, true), calendar_id: calendarId }), 'Termin angelegt');
    }
    const o = occ!;
    if (scope === 'single') {
      // Einzelnes Vorkommen: Einzeländerung direkt bearbeiten oder neu anlegen
      const data = payload(t.start, t.end, false);
      return run(
        () => (isOverride ? api.updateEvent(o.id, data) : api.updateEvent(o.id, data, o.start)),
        'Termin geändert',
      );
    }
    if (isOverride) {
      // Einzeländerung → Serie: nur Inhalte übertragen, Zeiten der Serie bleiben unverändert
      const data: EventInput = {
        title: title.trim(),
        member_ids: memberIds,
        location: location.trim() || null,
        description: description.trim() || null,
      };
      return run(() => api.updateEvent(o.series_id!, data), 'Serie geändert');
    }
    if (isSeriesOccurrence) {
      // Ganze Serie: Verschiebung relativ zum angezeigten Vorkommen auf die Serie übertragen
      const seriesId = o.series_id!;
      return run(async () => {
        const master = await api.event(seriesId);
        const shown = occurrenceRange(o);
        const masterRange = occurrenceRange(master);
        const delta = t.start.getTime() - shown.start.getTime();
        const duration = t.end.getTime() - t.start.getTime();
        let start = new Date(masterRange.start.getTime() + delta);
        if (allDay) start = parseDate(toDateString(start));   // DST-sicher auf Tagesgrenze
        const end = new Date(start.getTime() + duration);
        const data = payload(start, allDay ? addDays(start, Math.round(duration / 86_400_000)) : end, true);
        await api.updateEvent(seriesId, { ...data, calendar_id: calendarId });
      }, 'Serie geändert');
    }
    return run(() => api.updateEvent(o.id, { ...payload(t.start, t.end, true), calendar_id: calendarId }), 'Termin geändert');
  }

  function askDelete() {
    if (isSeriesOccurrence || isOverride) pending = { action: 'delete' };
    else confirmDelete = true;
  }

  function doDelete(scope: Scope) {
    const o = occ!;
    pending = null;
    if (scope === 'single') {
      return run(() => (isOverride ? api.deleteEvent(o.id) : api.deleteEvent(o.id, o.start)), 'Termin abgesagt');
    }
    return run(() => api.deleteEvent(o.series_id ?? o.id), o.series_id ? 'Serie gelöscht' : 'Termin gelöscht');
  }

  const dialogTitle = $derived(isNew ? 'Neuer Termin' : readOnly ? 'Termin' : 'Termin bearbeiten');
</script>

{#if editor.open}
  <Modal title={dialogTitle} onclose={() => editor.close()}>
    {#if pending}
      <div class="scope">
        <p>
          {pending.action === 'save' ? 'Änderung übernehmen für …' : 'Löschen …'}
        </p>
        <button class="btn" onclick={() => (pending!.action === 'save' ? doSave('single') : doDelete('single'))}>
          Nur diesen Termin
        </button>
        <button class="btn" onclick={() => (pending!.action === 'save' ? doSave('series') : doDelete('series'))}>
          Alle Termine der Serie
        </button>
        <button class="btn ghost" onclick={() => (pending = null)}>Abbrechen</button>
      </div>
    {:else}
      <form class="form" onsubmit={(e) => { e.preventDefault(); save(); }}>
        <input class="title" type="text" placeholder="Titel" bind:value={title} disabled={readOnly} maxlength="300" />

        <label class="switch">
          <input type="checkbox" bind:checked={allDay} disabled={readOnly} />
          Ganztägig
        </label>

        <div class="row">
          <span class="lbl">Beginn</span>
          <input type="date" bind:value={startDate} disabled={readOnly} required />
          {#if !allDay}<input type="time" bind:value={startTime} disabled={readOnly} step="300" required />{/if}
        </div>
        <div class="row">
          <span class="lbl">Ende</span>
          <input type="date" bind:value={endDate} disabled={readOnly} required />
          {#if !allDay}<input type="time" bind:value={endTime} disabled={readOnly} step="300" required />{/if}
        </div>

        {#if app.members.length}
          <div class="row wrap">
            <span class="lbl">Wer</span>
            {#each app.members as m (m.id)}
              <button
                type="button"
                class="member"
                class:on={memberIds.includes(m.id)}
                style:--c={m.color}
                onclick={() => toggleMember(m.id)}
                disabled={readOnly}
                aria-pressed={memberIds.includes(m.id)}
              >{m.avatar ? `${m.avatar} ` : ''}{m.name}</button>
            {/each}
          </div>
        {/if}

        {#if !isOverride}
          <div class="row">
            <span class="lbl">Wiederholen</span>
            {#if readOnly}
              <span>{describeRrule(originalRule)}</span>
            {:else}
              <select bind:value={repeat}>
                {#each Object.entries(REPEAT_LABELS) as [key, label] (key)}
                  {#if key !== 'custom' || originalRule}
                    <option value={key}>{key === 'custom' ? `${label} (${originalRule})` : label}</option>
                  {/if}
                {/each}
              </select>
              {#if repeat !== 'none' && repeat !== 'custom'}
                <span class="lbl small">bis</span>
                <input type="date" bind:value={until} min={startDate} />
              {/if}
            {/if}
          </div>
        {/if}

        {#if app.calendars.length > 1 && !isOverride}
          <div class="row">
            <span class="lbl">Kalender</span>
            <select bind:value={calendarId} disabled={readOnly}>
              {#each readOnly ? app.calendars : app.writableCalendars as c (c.id)}
                <option value={c.id}>{c.name}</option>
              {/each}
            </select>
          </div>
        {/if}

        <input type="text" placeholder="Ort" bind:value={location} disabled={readOnly} maxlength="500" />
        <textarea placeholder="Notiz" bind:value={description} disabled={readOnly} rows="2"></textarea>

        {#if error}<p class="error" role="alert">{error}</p>{/if}

        {#if confirmDelete}
          <div class="confirm">
            <span>Termin wirklich löschen?</span>
            <button type="button" class="btn danger" onclick={() => doDelete('series')} disabled={busy}>Löschen</button>
            <button type="button" class="btn ghost" onclick={() => (confirmDelete = false)}>Abbrechen</button>
          </div>
        {/if}

        <div class="actions">
          {#if !isNew && !readOnly}
            <button type="button" class="btn danger ghost" onclick={askDelete} disabled={busy}>Löschen</button>
          {/if}
          <span class="spacer"></span>
          <button type="button" class="btn ghost" onclick={() => editor.close()}>{readOnly ? 'Schließen' : 'Abbrechen'}</button>
          {#if !readOnly}
            <button type="submit" class="btn primary" disabled={busy}>Speichern</button>
          {/if}
        </div>
      </form>
    {/if}
  </Modal>
{/if}

<style>
  .form { display: flex; flex-direction: column; gap: 12px; }
  input, select, textarea {
    font: inherit;
    color: inherit;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 46px;
  }
  textarea { resize: vertical; }
  .title { font-size: 1.2rem; font-weight: 600; }
  .row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .row input[type='date'], .row input[type='time'], .row select { min-width: 0; }
  .row select { max-width: 240px; }
  .row.wrap { flex-wrap: wrap; }
  .lbl { width: 110px; color: var(--color-text-muted); flex: none; }
  .lbl.small { width: auto; }
  .switch { display: flex; align-items: center; gap: 10px; min-height: 40px; }
  .switch input { width: 24px; height: 24px; min-height: 0; }
  .member {
    min-height: 42px;
    padding: 0 14px;
    border-radius: 21px;
    border: 2px solid var(--c);
  }
  .member.on { background: var(--c); color: #fff; font-weight: 600; }
  .error { color: var(--color-accent); font-weight: 600; margin: 0; }
  .actions, .confirm { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
  .spacer { flex: 1; }
  .btn {
    min-height: 48px;
    padding: 0 20px;
    border-radius: var(--radius);
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    font-weight: 600;
  }
  .btn.primary { background: var(--color-accent); border-color: var(--color-accent); color: #fff; }
  .btn.ghost { background: transparent; }
  .btn.danger { color: #c0392b; border-color: #c0392b; }
  .btn.danger:not(.ghost) { background: #c0392b; color: #fff; }
  .scope { display: flex; flex-direction: column; gap: 12px; }
  .scope p { margin: 0 0 4px; font-weight: 600; }
</style>
