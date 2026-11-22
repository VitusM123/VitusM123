<script lang="ts">
  import EventChip from '../components/EventChip.svelte';
  import Toolbar from '../components/Toolbar.svelte';
  import { api } from '../lib/api';
  import { app } from '../lib/app.svelte';
  import { addDays, fmt, isWeekend, parseDate, sameDay, startOfWeek, toDateString, weekRangeLabel } from '../lib/dates';
  import { editor, newEventAt } from '../lib/editor.svelte';
  import { compareOccurrences } from '../lib/layout';
  import { swipe } from '../lib/swipe';
  import type { FamilyTable } from '../lib/types';

  let table = $state<FamilyTable | null>(null);

  const weekStart = $derived(startOfWeek(app.refDate, app.weekStartsOn));
  const showUnassigned = $derived(!!table?.days.some((d) => d.unassigned.length));
  const columns = $derived((table?.members.length ?? 0) + (showUnassigned ? 1 : 0));

  $effect(() => {
    const start = toDateString(weekStart);
    void app.eventsVersion;
    void app.members;
    let cancelled = false;
    api.familyTable(start, 7)
      .then((r) => { if (!cancelled) table = r; })
      .catch(() => { if (!cancelled) app.notify('Familienansicht konnte nicht geladen werden'); });
    return () => { cancelled = true; };
  });

  const prev = () => (app.refDate = addDays(app.refDate, -7));
  const next = () => (app.refDate = addDays(app.refDate, 7));
  const today = () => (app.refDate = new Date());
</script>

<div class="family" use:swipe={{ left: next, right: prev }}>
  <Toolbar title={weekRangeLabel(weekStart)} onprev={prev} onnext={next} ontoday={today} showFilter={false} />

  {#if table && table.members.length === 0}
    <div class="hint">
      <p>Noch keine Familienmitglieder angelegt.</p>
      <button class="btn" onclick={() => app.navigate('settings')}>Zu den Einstellungen</button>
    </div>
  {:else if table}
    <div class="table" style:--cols={columns}>
      <div class="corner"></div>
      {#each table.members as m (m.id)}
        <div class="mhead" style:--c={m.color}>
          <span class="avatar">{m.avatar ?? m.name.slice(0, 1)}</span>
          <span class="name">{m.name}</span>
        </div>
      {/each}
      {#if showUnassigned}
        <div class="mhead all"><span class="name">Alle</span></div>
      {/if}

      {#each table.days as day (day.date)}
        {@const d = parseDate(day.date)}
        {@const isToday = sameDay(d, app.now)}
        <div class="dayhead" class:today={isToday} class:weekend={isWeekend(d)}>
          <span class="wd">{fmt.weekdayShort(d)}</span>
          <span class="date">{d.getDate()}.{d.getMonth() + 1}.</span>
        </div>
        {#each table.members as m (m.id)}
          <div
            class="cell"
            class:today={isToday}
            class:weekend={isWeekend(d)}
            role="button"
            tabindex="-1"
            onclick={() => editor.openNew(newEventAt(d, 9, 0, [m.id]))}
            onkeydown={() => {}}
          >
            {#each [...(day.cells[String(m.id)] ?? [])].sort(compareOccurrences) as occ (occ.occurrence_id)}
              <EventChip {occ} hideMembers color={m.color} />
            {/each}
          </div>
        {/each}
        {#if showUnassigned}
          <div
            class="cell"
            class:today={isToday}
            class:weekend={isWeekend(d)}
            role="button"
            tabindex="-1"
            onclick={() => editor.openNew(newEventAt(d))}
            onkeydown={() => {}}
          >
            {#each day.unassigned as occ (occ.occurrence_id)}
              <EventChip {occ} />
            {/each}
          </div>
        {/if}
      {/each}
    </div>
  {/if}
</div>

<style>
  .family { height: 100%; display: flex; flex-direction: column; }
  .table {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: 76px repeat(var(--cols), minmax(0, 1fr));
    grid-template-rows: auto repeat(7, minmax(0, 1fr));
    gap: 1px;
    background: var(--color-border);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .corner, .mhead, .dayhead, .cell { background: var(--color-surface); }
  .mhead {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 8px 4px;
    border-bottom: 4px solid var(--c, var(--color-border));
    font-weight: 700;
  }
  .avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--c);
    color: #fff;
    font-size: 1rem;
  }
  .mhead.all { color: var(--color-text-muted); }
  .dayhead {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    line-height: 1.2;
  }
  .dayhead .wd { font-size: 0.75rem; text-transform: uppercase; color: var(--color-text-muted); }
  .dayhead .date { font-weight: 700; }
  .dayhead.today .date { color: var(--color-accent); }
  .weekend { background: var(--color-weekend); }
  .today { background: var(--color-today); }
  .cell {
    padding: 4px;
    display: flex;
    flex-direction: column;
    gap: 3px;
    overflow: auto;
    min-height: 0;
    cursor: pointer;
  }
  .hint { text-align: center; padding: 40px; color: var(--color-text-muted); }
  .btn {
    min-height: 48px;
    padding: 0 20px;
    border-radius: var(--radius);
    background: var(--color-accent);
    color: #fff;
    font-weight: 600;
  }
</style>
