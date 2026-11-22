<script lang="ts">
  import PinPad from '../components/PinPad.svelte';
  import ActivitiesSettings from '../components/settings/ActivitiesSettings.svelte';
  import AccountsSettings from '../components/settings/AccountsSettings.svelte';
  import CalendarsSettings from '../components/settings/CalendarsSettings.svelte';
  import GeneralSettings from '../components/settings/GeneralSettings.svelte';
  import MembersSettings from '../components/settings/MembersSettings.svelte';
  import ThemePicker from '../components/ThemePicker.svelte';
  import { api, ApiError } from '../lib/api';
  import { app } from '../lib/app.svelte';

  let pinError = $state<string | null>(null);
  let pinStep = $state<'idle' | 'setup' | 'change-current' | 'change-new'>('idle');
  let currentPin = '';

  // Ohne PIN ist der Admin-Bereich offen (Ersteinrichtung)
  const unlocked = $derived(!app.auth.pin_set || app.auth.authenticated);

  async function login(pin: string) {
    try {
      app.auth = await api.login(pin);
      pinError = null;
    } catch (err) {
      pinError = err instanceof ApiError ? err.message : 'Anmeldung fehlgeschlagen';
    }
  }

  async function setup(pin: string) {
    try {
      app.auth = await api.setupPin(pin);
      pinStep = 'idle';
      app.notify('PIN gespeichert');
    } catch (err) {
      pinError = err instanceof ApiError ? err.message : 'Fehler';
    }
  }

  async function changeNew(pin: string) {
    try {
      app.auth = await api.changePin(currentPin, pin);
      app.notify('PIN geändert');
    } catch (err) {
      app.notify(err instanceof ApiError ? err.message : 'Fehler');
    }
    currentPin = '';
    pinStep = 'idle';
  }

  async function logout() {
    app.auth = await api.logout();
  }

  async function setDisplay(data: { screen_on?: boolean; brightness?: number }) {
    app.display = await api.setDisplay(data);
  }
</script>

<section class="settings">
  <h1>Einstellungen</h1>

  <h2>Farbschema</h2>
  <ThemePicker />

  <h2>Bildschirm</h2>
  <div class="display">
    <label>
      Helligkeit
      <input type="range" min="10" max="100" step="10" value={app.display.brightness}
        onchange={(e) => setDisplay({ brightness: Number(e.currentTarget.value) })} />
    </label>
    <button class="btn" onclick={() => setDisplay({ screen_on: false })}>Bildschirm ausschalten</button>
  </div>

  {#if !unlocked}
    <h2>Verwaltung</h2>
    <div class="lock">
      <PinPad label="Admin-PIN eingeben, um Familienmitglieder, Kalender und Einstellungen zu ändern"
        submitLabel="Entsperren" onsubmit={login} error={pinError} />
    </div>
  {:else}
    <h2>Familienmitglieder</h2>
    <MembersSettings />

    <h2>Verknüpfte Konten</h2>
    <AccountsSettings />

    <h2>Kalender</h2>
    <CalendarsSettings />

    <h2>Wohnort & Freizeitaktivitäten</h2>
    <ActivitiesSettings />

    <h2>Allgemein</h2>
    <GeneralSettings />

    <h2>Admin-PIN</h2>
    {#if pinStep === 'setup'}
      <PinPad label="Neue PIN (mind. 4 Ziffern)" submitLabel="Speichern" onsubmit={setup} error={pinError} />
    {:else if pinStep === 'change-current'}
      <PinPad label="Aktuelle PIN" submitLabel="Weiter" onsubmit={(p) => { currentPin = p; pinStep = 'change-new'; }} />
    {:else if pinStep === 'change-new'}
      <PinPad label="Neue PIN" submitLabel="Speichern" onsubmit={changeNew} />
    {:else if !app.auth.pin_set}
      <p class="warn">Noch keine PIN gesetzt – die Verwaltung ist für alle offen.</p>
      <button class="btn primary" onclick={() => (pinStep = 'setup')}>PIN festlegen</button>
    {:else}
      <div class="row">
        <button class="btn" onclick={() => (pinStep = 'change-current')}>PIN ändern</button>
        <button class="btn" onclick={logout}>Sperren</button>
      </div>
    {/if}
  {/if}

  <h2>Info</h2>
  <dl>
    <dt>Version</dt><dd>{app.info?.version ?? '–'}</dd>
    <dt>Zeitzone</dt><dd>{app.info?.timezone ?? '–'}</dd>
    <dt>Kiosk-Modus</dt><dd>{app.kiosk ? 'an (Bildschirmtastatur aktiv)' : 'aus'}</dd>
  </dl>
</section>

<style>
  .settings { max-width: 980px; margin: 0 auto; padding-bottom: calc(24px + var(--osk-h, 0px)); }
  h1 { margin-top: 0; }
  h2 { margin: 28px 0 12px; font-size: 1.1rem; color: var(--color-text-muted); }
  .display, .row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .display label { display: flex; align-items: center; gap: 12px; }
  input[type='range'] { width: 260px; height: 36px; accent-color: var(--color-accent); }
  .lock {
    padding: 20px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    text-align: center;
  }
  .btn {
    min-height: 48px;
    padding: 0 18px;
    border-radius: var(--radius);
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    font-weight: 600;
  }
  .btn.primary { background: var(--color-accent); border-color: var(--color-accent); color: #fff; }
  .warn { color: var(--color-accent); font-weight: 600; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; }
  dt { color: var(--color-text-muted); }
  dd { margin: 0; }
</style>
