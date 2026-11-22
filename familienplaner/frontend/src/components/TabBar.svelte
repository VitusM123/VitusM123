<script lang="ts">
  import { app } from '../lib/app.svelte';
  import type { ViewId } from '../lib/types';

  const tabs: { id: ViewId; label: string; icon: string }[] = [
    { id: 'month', label: 'Monat', icon: '▦' },
    { id: 'week', label: 'Woche', icon: '▤' },
    { id: 'family', label: 'Familie', icon: '☷' },
    { id: 'activities', label: 'Aktivitäten', icon: '✦' },
    { id: 'settings', label: 'Einstellungen', icon: '⚙' },
  ];
</script>

<nav>
  {#each tabs as tab (tab.id)}
    <button class:active={app.view === tab.id} onclick={() => app.navigate(tab.id)} aria-label={tab.label}>
      <span class="icon" aria-hidden="true">{tab.icon}</span>
      <span class="label">{tab.label}</span>
    </button>
  {/each}
</nav>

<style>
  nav {
    height: var(--tabbar-h);
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    background: var(--color-surface);
    border-top: 1px solid var(--color-border);
  }
  button {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    color: var(--color-text-muted);
    min-height: 48px;          /* Touch-Ziel */
  }
  button.active { color: var(--color-accent); font-weight: 600; }
  .icon { font-size: 1.4rem; line-height: 1; }
  .label { font-size: 0.8rem; }
</style>
