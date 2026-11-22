<script lang="ts">
  import { untrack } from 'svelte';
  import EventChip from '../components/EventChip.svelte';
  import Toolbar from '../components/Toolbar.svelte';
  import { api } from '../lib/api';
  import { app } from '../lib/app.svelte';
  import { addDays, fmt, isWeekend, sameDay, startOfWeek, toDateString, toLocalIso, weekRangeLabel } from '../lib/dates';
  import { editor, newEventAt } from '../lib/editor.svelte';
  import { bucketByDay, eventColor, layoutDay } from '../lib/layout';
  import { swipe } from '../lib/swipe';
  import type { EventOccurrence } from '../lib/types';

  const HOUR_H = 52;          // Pixel pro Stunde
  const SNAP_MIN = 30;

  let events = $state<EventOccurrence[]>([]);
  let scroller = $state<HTMLElement | null>(null);

  const weekStart = $derived(startOfWeek(app.refDate, app.weekStartsOn));
  const days = $derived(Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)));
  const byDay = $derived(bucketByDay(events));
  const allDayByDay = $derived(days.map((d) => (byDay.get(toDateString(d)) ?? []).filter((e) => e.all_day)));
  const hasAllDay = $derived(allDayByDay.some((l) => l.length));
  const positioned = $derived(days.map((d) => layoutDay(byDay.get(toDateString(d)) ?? [], d)));
  const nowTop = $derived((app.now.getHours() * 60 + app.now.getMinutes()) / 60 * HOUR_H);

  $effect(() => {
    const start = weekStart;
    const filter = app.memberFilter.length ? [...app.memberFilter] : undefined;
    void app.eventsVersion;
    let cancelled = false;
    api.events(toLocalIso(start), toLocalIso(addDays(start, 7)), filter)
      .then((r) => { if (!cancelled) events = r; })
      .catch(() => { if (!cancelled) app.notify('Termine konnten nicht geladen werden'); });
    return () => { cancelled = true; };
  });

  // Beim Öffnen so scrollen, dass der Tag ab 7 Uhr (frühmorgens: ab jetzt) sichtbar ist.
  // Nur einmal pro Anzeige – die minütliche Uhrzeit-Aktualisierung soll nicht zurückscrollen.
  $effect(() => {
    if (!scroller) return;
    const hour = untrack(() => app.now.getHours());
    scroller.scrollTop = Math.min(Math.max(hour - 1, 0), 7) * HOUR_H;
  });

  const prev = () => (app.refDate = addDays(app.refDate, -7));
  const next = () => (app.refDate = addDays(app.refDate, 7));
  const today = () => (app.refDate = new Date());

  function newAt(day: Date, e: MouseEvent) {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const minutes = Math.floor(((e.clientY - rect.top) / HOUR_H) * 60 / SNAP_MIN) * SNAP_MIN;
    const clamped = Math.min(Math.max(minutes, 0), 23 * 60);
    editor.openNew(newEventAt(day, Math.floor(clamped / 60), clamped % 60, [...app.memberFilter]));
  }

  function newAllDay(day: Date) {
    editor.openNew({ start: day, end: addDays(day, 1), allDay: true, memberIds: [...app.memberFilter] });
  }

  const hours = Array.from({ length: 24 }, (_, h) => h);
</script>

<div class="week" use:swipe={{ left: next, right: prev }}>
  <Toolbar title={weekRangeLabel(weekStart)} onprev={prev} onnext={next} ontoday={today} />

  <div class="frame">
    <div class="head">
      <div class="gutter"></div>
      {#each days as day (day.getTime())}
        <div class="dayhead" class:today={sameDay(day, app.now)} class:weekend={isWeekend(day)}>
          <span class="wd">{fmt.weekdayShort(day)}</span>
          <span class="date">{day.getDate()}</span>
        </div>
      {/each}
    </div>

    <div class="allday" class:empty={!hasAllDay}>
      <div class="gutter label">ganztägig</div>
      {#each days as day, i (day.getTime())}
        <div class="allday-cell" role="button" tabindex="-1" onclick={() => newAllDay(day)} onkeydown={() => {}}>
          {#each allDayByDay[i] as occ (occ.occurrence_id)}
            <EventChip {occ} showTime={false} />
          {/each}
        </div>
      {/each}
    </div>

    <div class="scroll" bind:this={scroller}>
      <div class="body" style:height="{24 * HOUR_H}px">
        <div class="gutter hours">
          {#each hours as h (h)}
            <span style:top="{h * HOUR_H}px">{h === 0 ? '' : `${String(h).padStart(2, '0')}:00`}</span>
          {/each}
        </div>
        {#each days as day, i (day.getTime())}
          <div
            class="col"
            class:weekend={isWeekend(day)}
            class:today={sameDay(day, app.now)}
            style:--hour="{HOUR_H}px"
            role="button"
            tabindex="-1"
            onclick={(e) => newAt(day, e)}
            onkeydown={() => {}}
          >
            {#each positioned[i] as p (p.occ.occurrence_id)}
              {@const color = eventColor(p.occ, app.memberColor)}
              {@const short = (p.endMin - p.startMin) < 45}
              <button
                class="ev"
                class:short
                class:cont-before={p.continuesBefore}
                class:cont-after={p.continuesAfter}
                style:--c={color}
                style:top="{(p.startMin / 60) * HOUR_H}px"
                style:height="{((p.endMin - p.startMin) / 60) * HOUR_H - 2}px"
                style:left="calc({(p.column / p.columns) * 100}% + 2px)"
                style:width="calc({100 / p.columns}% - 4px)"
                onclick={(e) => { e.stopPropagation(); editor.openEdit(p.occ); }}
              >
                <span class="t">{p.occ.title}</span>
                {#if !short}
                  <span class="time">
                    {fmt.time(new Date(p.occ.start))} – {fmt.time(new Date(p.occ.end))}
                  </span>
                  {#if p.occ.location}<span class="loc">{p.occ.location}</span>{/if}
                {/if}
                {#if p.occ.member_ids.length > 1}
                  <span class="dots">
                    {#each p.occ.member_ids as id (id)}
                      <span style:background={app.memberColor(id)}></span>
                    {/each}
                  </span>
                {/if}
              </button>
            {/each}
            {#if sameDay(day, app.now)}
              <div class="now" style:top="{nowTop}px"></div>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  </div>
</div>

<style>
  .week { height: 100%; display: flex; flex-direction: column; }
  .frame {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .head, .allday, .body { display: grid; grid-template-columns: 58px repeat(7, minmax(0, 1fr)); }
  .head { border-bottom: 1px solid var(--color-border); }
  .dayhead { display: flex; align-items: baseline; justify-content: center; gap: 6px; padding: 6px 0; }
  .dayhead .wd { color: var(--color-text-muted); font-size: 0.8rem; text-transform: uppercase; }
  .dayhead .date { font-weight: 700; font-size: 1.15rem; }
  .dayhead.today .date {
    background: var(--color-accent);
    color: #fff;
    border-radius: 14px;
    padding: 0 8px;
  }
  .weekend { background: var(--color-weekend); }
  .allday { border-bottom: 1px solid var(--color-border); max-height: 112px; overflow: auto; }
  .allday.empty .allday-cell { min-height: 30px; }
  .allday-cell {
    padding: 3px;
    display: flex;
    flex-direction: column;
    gap: 3px;
    border-left: 1px solid var(--color-border);
    min-height: 34px;
  }
  .label { font-size: 0.65rem; color: var(--color-text-muted); align-self: center; text-align: right; padding-right: 6px; }
  .scroll { flex: 1; overflow-y: auto; min-height: 0; }
  .body { position: relative; }
  .hours { position: relative; }
  .hours span {
    position: absolute;
    right: 6px;
    transform: translateY(-50%);
    font-size: 0.72rem;
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
  }
  .col {
    position: relative;
    border-left: 1px solid var(--color-border);
    background-image: repeating-linear-gradient(
      to bottom, transparent 0, transparent calc(var(--hour) - 1px), var(--color-border) calc(var(--hour) - 1px), var(--color-border) var(--hour)
    );
  }
  .col.today { background-color: color-mix(in srgb, var(--color-today) 45%, transparent); }
  .ev {
    position: absolute;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    overflow: hidden;
    padding: 3px 6px;
    border-radius: 6px;
    border-left: 4px solid var(--c);
    background: color-mix(in srgb, var(--c) 20%, var(--color-surface));
    text-align: left;
    font-size: 0.78rem;
    line-height: 1.25;
    z-index: 1;
  }
  .ev.short { flex-direction: row; gap: 6px; align-items: center; }
  .ev.cont-before { border-top-left-radius: 0; border-top-right-radius: 0; }
  .ev.cont-after { border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
  .t { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
  .time, .loc { color: var(--color-text-muted); font-size: 0.72rem; white-space: nowrap; }
  .dots { display: flex; gap: 3px; margin-top: 2px; }
  .dots span { width: 8px; height: 8px; border-radius: 50%; }
  .now {
    position: absolute;
    left: 0;
    right: 0;
    height: 2px;
    background: #e53935;
    z-index: 2;
    pointer-events: none;
  }
  .now::before {
    content: '';
    position: absolute;
    left: -5px;
    top: -4px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #e53935;
  }
  :global(:root[data-mode='eink']) .ev { background: var(--color-surface); border: 1px solid var(--color-text); border-left-width: 4px; }
</style>
