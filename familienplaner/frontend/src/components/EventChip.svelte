<script lang="ts">
  import { app } from '../lib/app.svelte';
  import { fmt, occurrenceRange } from '../lib/dates';
  import { editor } from '../lib/editor.svelte';
  import { eventColor } from '../lib/layout';
  import type { EventOccurrence } from '../lib/types';

  interface Props {
    occ: EventOccurrence;
    showTime?: boolean;
    /** In Ansichten pro Person: Personenpunkte ausblenden */
    hideMembers?: boolean;
    /** Feste Farbe (z. B. Farbe der Spalte in der Familienansicht) */
    color?: string;
  }
  let { occ, showTime = true, hideMembers = false, color: fixedColor }: Props = $props();

  const color = $derived(fixedColor ?? eventColor(occ, app.memberColor));
  const time = $derived(occ.all_day ? '' : fmt.time(occurrenceRange(occ).start));
  const members = $derived(hideMembers || occ.member_ids.length < 2 ? [] : occ.member_ids.map((id) => app.memberById(id)));

  function open(e: Event) {
    e.stopPropagation();
    editor.openEdit(occ);
  }
</script>

<button class="chip" class:allday={occ.all_day} style:--c={color} onclick={open} title={occ.title}>
  {#if showTime && time}<span class="time">{time}</span>{/if}
  <span class="title">{occ.title}</span>
  {#if occ.recurring}<span class="rec" aria-label="wiederkehrend">↻</span>{/if}
  {#each members as m (m?.id)}
    {#if m}<span class="dot" style:background={m.color}></span>{/if}
  {/each}
</button>

<style>
  .chip {
    display: flex;
    align-items: center;
    gap: 5px;
    width: 100%;
    min-height: 26px;
    padding: 2px 6px;
    border-radius: 6px;
    border-left: 4px solid var(--c);
    background: color-mix(in srgb, var(--c) 14%, var(--color-surface));
    font-size: 0.78rem;
    text-align: left;
    overflow: hidden;
  }
  .chip.allday { background: var(--c); color: #fff; border-left-color: var(--c); }
  .time { font-variant-numeric: tabular-nums; font-weight: 600; flex: none; }
  .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .rec { opacity: 0.7; flex: none; }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; border: 1px solid var(--color-surface); }
  :global(:root[data-mode='eink']) .chip { background: var(--color-surface); border: 1px solid var(--color-text); border-left-width: 4px; }
  :global(:root[data-mode='eink']) .chip.allday { color: var(--color-text); }
</style>
