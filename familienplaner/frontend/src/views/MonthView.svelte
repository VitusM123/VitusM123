<script lang="ts">
  import EventChip from '../components/EventChip.svelte';
  import Toolbar from '../components/Toolbar.svelte';
  import { api } from '../lib/api';
  import { app } from '../lib/app.svelte';
  import { addDays, addMonths, fmt, isWeekend, monthGrid, sameDay, toDateString, toLocalIso } from '../lib/dates';
  import { editor, newEventAt } from '../lib/editor.svelte';
  import { bucketByDay } from '../lib/layout';
  import { swipe } from '../lib/swipe';
  import type { EventOccurrence } from '../lib/types';

  let events = $state<EventOccurrence[]>([]);
  let loading = $state(false);

  const days = $derived(monthGrid(app.refDate, app.weekStartsOn));
  const weeks = $derived(days.length / 7);
  const byDay = $derived(bucketByDay(events));
  const weekdays = $derived(days.slice(0, 7).map(fmt.weekdayShort));
  // Wie viele Chips passen in eine Zelle (5 oder 6 Wochen auf ~600 px)
  const maxChips = $derived(weeks >= 6 ? 3 : 4);

  $effect(() => {
    const start = days[0];
    const end = addDays(days[days.length - 1], 1);
    const filter = app.memberFilter.length ? [...app.memberFilter] : undefined;
    void app.eventsVersion;
    let cancelled = false;
    loading = true;
    api.events(toLocalIso(start), toLocalIso(end), filter)
      .then((r) => { if (!cancelled) events = r; })
      .catch(() => { if (!cancelled) app.notify('Termine konnten nicht geladen werden'); })
      .finally(() => { if (!cancelled) loading = false; });
    return () => { cancelled = true; };
  });

  const prev = () => (app.refDate = addMonths(app.refDate, -1));
  const next = () => (app.refDate = addMonths(app.refDate, 1));
  const today = () => (app.refDate = new Date());

  function openWeek(day: Date) {
    app.refDate = day;
    app.navigate('week');
  }
</script>

<div class="month" use:swipe={{ left: next, right: prev }}>
  <Toolbar title={fmt.monthYear(app.refDate)} onprev={prev} onnext={next} ontoday={today} />

  <div class="grid" style:--weeks={weeks} aria-busy={loading}>
    {#each weekdays as wd (wd)}
      <div class="wd">{wd}</div>
    {/each}
    {#each days as day (day.getTime())}
      {@const list = byDay.get(toDateString(day)) ?? []}
      {@const other = day.getMonth() !== app.refDate.getMonth()}
      <div
        class="cell"
        class:other
        class:weekend={isWeekend(day)}
        class:today={sameDay(day, app.now)}
        role="button"
        tabindex="-1"
        onclick={() => editor.openNew(newEventAt(day, 9, 0, [...app.memberFilter]))}
        onkeydown={() => {}}
      >
        <button class="num" onclick={(e) => { e.stopPropagation(); openWeek(day); }} aria-label={fmt.full(day)}>
          {day.getDate()}
        </button>
        <div class="events">
          {#each list.slice(0, list.length > maxChips ? maxChips - 1 : maxChips) as occ (occ.occurrence_id)}
            <EventChip {occ} />
          {/each}
          {#if list.length > maxChips}
            <button class="more" onclick={(e) => { e.stopPropagation(); openWeek(day); }}>
              + {list.length - maxChips + 1} weitere
            </button>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>

<style>
  .month { height: 100%; display: flex; flex-direction: column; }
  .grid {
    flex: 1;
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    grid-template-rows: auto repeat(var(--weeks), minmax(0, 1fr));
    gap: 1px;
    background: var(--color-border);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    overflow: hidden;
    min-height: 0;
  }
  .wd {
    background: var(--color-surface);
    text-align: center;
    padding: 6px 0;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--color-text-muted);
    text-transform: uppercase;
  }
  .cell {
    background: var(--color-surface);
    padding: 4px;
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-height: 0;
    overflow: hidden;
    cursor: pointer;
  }
  .cell.weekend { background: var(--color-weekend); }
  .cell.other { opacity: 0.5; }
  .num {
    align-self: flex-start;
    min-width: 30px;
    height: 30px;
    padding: 0 6px;
    border-radius: 15px;
    font-weight: 600;
    font-size: 0.9rem;
  }
  .today .num { background: var(--color-accent); color: #fff; }
  .cell.today { background: var(--color-today); }
  .events { display: flex; flex-direction: column; gap: 3px; min-height: 0; }
  .more {
    font-size: 0.75rem;
    color: var(--color-text-muted);
    text-align: left;
    padding: 2px 6px;
    min-height: 24px;
  }
</style>
