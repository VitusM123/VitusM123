<script lang="ts">
  import { onMount } from 'svelte';
  import EventDialog from './components/EventDialog.svelte';
  import Header from './components/Header.svelte';
  import OnScreenKeyboard from './components/OnScreenKeyboard.svelte';
  import ScreenOff from './components/ScreenOff.svelte';
  import TabBar from './components/TabBar.svelte';
  import Toast from './components/Toast.svelte';
  import { api } from './lib/api';
  import { app } from './lib/app.svelte';
  import { editor } from './lib/editor.svelte';
  import ActivitiesView from './views/ActivitiesView.svelte';
  import EInkView from './views/EInkView.svelte';
  import FamilyTableView from './views/FamilyTableView.svelte';
  import MonthView from './views/MonthView.svelte';
  import SettingsView from './views/SettingsView.svelte';
  import WeekView from './views/WeekView.svelte';

  const IDLE_MS = 5 * 60_000;   // Wanddisplay: nach 5 min ohne Bedienung zurück zu „Heute“

  onMount(() => {
    void app.init();
    let timer: ReturnType<typeof setTimeout>;
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (!app.kiosk || editor.open) return;
        app.resetToToday();
        // Verwaltung am Wanddisplay nach Inaktivität wieder sperren
        if (app.auth.pin_set && app.auth.authenticated) void api.logout().then((a) => (app.auth = a));
      }, IDLE_MS);
    };
    reset();
    window.addEventListener('pointerdown', reset, { passive: true });
    window.addEventListener('keydown', reset);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('pointerdown', reset);
      window.removeEventListener('keydown', reset);
    };
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
  <EventDialog />
  <Toast />
  {#if app.kiosk}<OnScreenKeyboard />{/if}
  <ScreenOff />
{/if}

<style>
  .shell {
    height: 100%;
    display: grid;
    grid-template-rows: var(--header-h) minmax(0, 1fr) var(--tabbar-h);
  }
  main {
    overflow: auto;
    padding: 12px 16px;
    min-height: 0;
  }
  .error {
    padding: 16px;
    border: 2px solid var(--color-accent);
    border-radius: var(--radius);
    background: var(--color-surface);
  }
</style>
