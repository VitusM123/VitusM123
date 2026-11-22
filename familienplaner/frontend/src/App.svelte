<script lang="ts">
  import { onMount } from 'svelte';
  import Header from './components/Header.svelte';
  import ScreenOff from './components/ScreenOff.svelte';
  import TabBar from './components/TabBar.svelte';
  import { app } from './lib/app.svelte';
  import ActivitiesView from './views/ActivitiesView.svelte';
  import EInkView from './views/EInkView.svelte';
  import FamilyTableView from './views/FamilyTableView.svelte';
  import MonthView from './views/MonthView.svelte';
  import SettingsView from './views/SettingsView.svelte';
  import WeekView from './views/WeekView.svelte';

  onMount(() => {
    void app.init();
  });
</script>

{#if app.view === 'eink'}
  <EInkView />
{:else}
  <div class="shell">
    <Header />
    <main>
      {#if app.error}
        <div class="error">{app.error}</div>
      {:else if app.view === 'month'}
        <MonthView />
      {:else if app.view === 'week'}
        <WeekView />
      {:else if app.view === 'family'}
        <FamilyTableView />
      {:else if app.view === 'activities'}
        <ActivitiesView />
      {:else if app.view === 'settings'}
        <SettingsView />
      {/if}
    </main>
    <TabBar />
  </div>
  <ScreenOff />
{/if}

<style>
  .shell {
    height: 100%;
    display: grid;
    grid-template-rows: var(--header-h) 1fr var(--tabbar-h);
  }
  main {
    overflow: auto;
    padding: 16px 20px;
  }
  .error {
    padding: 16px;
    border: 2px solid var(--color-accent);
    border-radius: var(--radius);
    background: var(--color-surface);
  }
</style>
