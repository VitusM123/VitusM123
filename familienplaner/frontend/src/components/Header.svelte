<script lang="ts">
  import { app } from '../lib/app.svelte';

  let now = $state(new Date());
  $effect(() => {
    const timer = setInterval(() => (now = new Date()), 1000 * 15);
    return () => clearInterval(timer);
  });

  const time = $derived(now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }));
  const day = $derived(now.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' }));
  const syncLabel = $derived.by(() => {
    if (!app.connected) return 'Offline';
    if (app.sync?.state === 'running') return 'Synchronisiere …';
    if (app.sync?.state === 'error') return 'Sync-Fehler';
    return '';
  });
</script>

<header>
  <div class="clock">
    <span class="time">{time}</span>
    <span class="day">{day}</span>
  </div>
  {#if syncLabel}
    <span class="status" class:warn={!app.connected || app.sync?.state === 'error'}>{syncLabel}</span>
  {/if}
</header>

<style>
  header {
    height: var(--header-h);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
  }
  .clock { display: flex; align-items: baseline; gap: 14px; }
  .time { font-size: 1.8rem; font-weight: 700; font-variant-numeric: tabular-nums; }
  .day { color: var(--color-text-muted); }
  .status { font-size: 0.85rem; color: var(--color-text-muted); }
  .status.warn { color: var(--color-accent); font-weight: 600; }
</style>
