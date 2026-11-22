<script lang="ts">
  import { api, ApiError } from '../../lib/api';
  import { app } from '../../lib/app.svelte';
  import type { AccountInfo, GoogleConfig } from '../../lib/types';

  let accounts = $state<AccountInfo[]>([]);
  let config = $state<GoogleConfig | null>(null);
  let clientId = $state('');
  let clientSecret = $state('');
  let pasteMode = $state(false);
  let pasted = $state('');
  let busy = $state(false);
  let confirmRemove = $state<number | null>(null);
  let showSetup = $state(false);
  let icloudForm = $state(false);
  let appleId = $state('');
  let appPassword = $state('');
  let serverUrl = $state('');
  let advanced = $state(false);
  let icloudError = $state<string | null>(null);

  const external = $derived(accounts.filter((a) => a.provider !== 'local'));

  async function load() {
    [accounts, config] = await Promise.all([api.accounts(), api.googleConfig()]);
  }
  // Beim Öffnen und nach jedem Sync (auch im Hintergrund) Status aktualisieren
  $effect(() => {
    void app.sync?.last_run;
    void load();
  });

  async function guard(fn: () => Promise<void>) {
    busy = true;
    try {
      await fn();
    } catch (err) {
      app.notify(err instanceof ApiError ? err.message : 'Aktion fehlgeschlagen');
    } finally {
      busy = false;
    }
  }

  const saveConfig = (e: SubmitEvent) => {
    e.preventDefault();
    return guard(async () => {
      config = await api.setGoogleConfig(clientId, clientSecret);
      clientId = clientSecret = '';
      showSetup = false;
      app.notify('Google-Zugang gespeichert');
    });
  };

  const connect = () => guard(async () => {
    const { auth_url } = await api.googleStart();
    if (app.kiosk) {
      window.location.href = auth_url;      // am Pi: Google leitet direkt zurück
    } else {
      window.open(auth_url, '_blank', 'noopener');
      pasteMode = true;
    }
  });

  const complete = (e: SubmitEvent) => {
    e.preventDefault();
    return guard(async () => {
      await api.googleComplete(pasted.trim());
      pasted = '';
      pasteMode = false;
      app.notify('Google verbunden – neue Termine landen künftig in Google (änderbar unter „Kalender“)');
      await load();
    });
  };

  function openICloud(prefill = '') {
    appleId = prefill;
    appPassword = '';
    icloudError = null;
    icloudForm = true;
  }

  async function connectICloud(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    icloudError = null;
    try {
      await api.icloudConnect(appleId, appPassword, advanced ? serverUrl : null);
      icloudForm = false;
      appPassword = '';
      app.notify('iCloud verbunden – neue Termine landen künftig in iCloud (änderbar unter „Kalender“)');
      await load();
      app.calendars = await api.calendars();
    } catch (err) {
      icloudError = err instanceof ApiError ? err.message : 'Verbindung fehlgeschlagen';
    } finally {
      busy = false;
    }
  }

  const syncNow = (id: number) => guard(async () => {
    app.sync = await api.syncAccount(id);
    await load();
  });

  const remove = (id: number) => guard(async () => {
    await api.deleteAccount(id);
    confirmRemove = null;
    await load();
    app.calendars = await api.calendars();
  });

  function ago(iso: string | null): string {
    if (!iso) return 'noch nie';
    const min = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
    if (min < 1) return 'gerade eben';
    if (min < 60) return `vor ${min} min`;
    return new Date(iso).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
  }
  const PROVIDER = { google: 'Google', icloud: 'iCloud', local: 'Lokal' } as const;
</script>

<div class="accounts">
  {#each external as a (a.id)}
    <div class="account" class:error={!!a.last_error}>
      <div class="info">
        <strong>{PROVIDER[a.provider]} · {a.display_name}</strong>
        <span class="muted">{a.calendar_count} Kalender · zuletzt synchronisiert {ago(a.last_sync)}</span>
        {#if a.last_error}<span class="err">⚠ {a.last_error}</span>{/if}
      </div>
      <div class="actions">
        <button class="btn" onclick={() => syncNow(a.id)} disabled={busy}>Jetzt synchronisieren</button>
        {#if a.last_error && a.provider === 'google'}
          <button class="btn primary" onclick={connect} disabled={busy}>Neu verbinden</button>
        {:else if a.last_error && a.provider === 'icloud'}
          <button class="btn primary" onclick={() => openICloud(a.display_name)} disabled={busy}>Neu verbinden</button>
        {/if}
        {#if confirmRemove === a.id}
          <button class="btn danger" onclick={() => remove(a.id)} disabled={busy}>Trennen bestätigen</button>
        {:else}
          <button class="btn ghost" onclick={() => (confirmRemove = a.id)}>Trennen</button>
        {/if}
      </div>
    </div>
  {/each}

  {#if config && !config.configured}
    <div class="box">
      <p><strong>Google-Kalender einrichten</strong> – einmalig wird ein eigener Google-Zugang (OAuth-Client) benötigt.</p>
      {#if showSetup}
        <ol class="steps">
          <li>Auf <code>console.cloud.google.com</code> ein Projekt anlegen und die <em>Google Calendar API</em> aktivieren.</li>
          <li>Unter „OAuth-Zustimmungsbildschirm“: Typ <em>Extern</em>, eigene E-Mail als Testnutzer eintragen, danach
            <em>„App veröffentlichen“</em> (sonst läuft die Anmeldung nach 7 Tagen ab).</li>
          <li>Unter „Anmeldedaten“ → „OAuth-Client-ID erstellen“ → Anwendungstyp <em>Desktop-App</em>.</li>
          <li>Client-ID und Client-Secret hier eintragen.</li>
        </ol>
        <form class="form" onsubmit={saveConfig}>
          <input type="text" placeholder="Client-ID (…apps.googleusercontent.com)" bind:value={clientId} autocomplete="off" />
          <input type="text" placeholder="Client-Secret" bind:value={clientSecret} autocomplete="off" />
          <div class="row">
            <button type="button" class="btn ghost" onclick={() => (showSetup = false)}>Abbrechen</button>
            <button type="submit" class="btn primary" disabled={busy || !clientId || !clientSecret}>Speichern</button>
          </div>
        </form>
      {:else}
        <button class="btn primary" onclick={() => (showSetup = true)}>Einrichten</button>
      {/if}
    </div>
  {:else if config}
    {#if pasteMode}
      <form class="box form" onsubmit={complete}>
        <p>
          Melde dich im neuen Tab bei Google an. Danach zeigt der Browser eine Fehlerseite
          (<code>127.0.0.1</code> nicht erreichbar) – das ist richtig so.
          <strong>Kopiere die komplette Adresse aus der Adresszeile</strong> und füge sie hier ein:
        </p>
        <input type="text" placeholder="http://127.0.0.1:8000/api/accounts/google/callback?state=…&code=…"
          bind:value={pasted} autocomplete="off" />
        <div class="row">
          <button type="button" class="btn ghost" onclick={() => (pasteMode = false)}>Abbrechen</button>
          <button type="submit" class="btn primary" disabled={busy || pasted.length < 10}>Verbinden</button>
        </div>
      </form>
    {:else}
      <div class="row">
        <button class="btn primary" onclick={connect} disabled={busy}>+ Google-Konto verbinden</button>
      </div>
    {/if}
  {/if}

  {#if icloudForm}
    <form class="box form" onsubmit={connectICloud}>
      <p><strong>iCloud-Kalender verbinden</strong></p>
      <ol class="steps">
        <li>Auf <code>account.apple.com</code> anmelden → <em>Anmeldung und Sicherheit</em> →
          <em>App-spezifische Passwörter</em> → neues Passwort „Familienplaner“ erstellen.</li>
        <li>Apple-ID und das erzeugte Passwort (Format <code>abcd-efgh-ijkl-mnop</code>) hier eintragen.
          Das normale Apple-ID-Passwort funktioniert nicht.</li>
      </ol>
      <input type="text" placeholder="Apple-ID (E-Mail)" bind:value={appleId} autocomplete="username" />
      <input type="password" placeholder="App-spezifisches Passwort" bind:value={appPassword} autocomplete="off" />
      <label class="adv"><input type="checkbox" bind:checked={advanced} /> Anderer CalDAV-Server (z. B. Nextcloud)</label>
      {#if advanced}
        <input type="text" placeholder="https://cloud.example.org/remote.php/dav" bind:value={serverUrl} />
      {/if}
      {#if icloudError}<p class="err" role="alert">⚠ {icloudError}</p>{/if}
      <div class="row">
        <button type="button" class="btn ghost" onclick={() => (icloudForm = false)}>Abbrechen</button>
        <button type="submit" class="btn primary" disabled={busy || !appleId || !appPassword}>
          {busy ? 'Verbinde …' : 'Verbinden'}
        </button>
      </div>
    </form>
  {:else}
    <div class="row">
      <button class="btn primary" onclick={() => openICloud()} disabled={busy}>+ iCloud-Kalender verbinden</button>
    </div>
  {/if}
</div>

<style>
  .accounts { display: flex; flex-direction: column; gap: 10px; }
  .account, .box {
    padding: 12px 14px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
  }
  .account { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; align-items: center; }
  .account.error { border-color: #c0392b; }
  .info { display: flex; flex-direction: column; gap: 2px; }
  .muted { color: var(--color-text-muted); font-size: 0.85rem; }
  .err { color: #c0392b; font-size: 0.85rem; font-weight: 600; }
  .actions, .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .form { display: flex; flex-direction: column; gap: 10px; }
  .form p, .box p { margin: 0 0 8px; }
  .adv { display: flex; align-items: center; gap: 8px; color: var(--color-text-muted); min-height: 40px; }
  .adv input { width: 22px; height: 22px; min-height: 0; }
  .steps { margin: 0 0 12px; padding-left: 22px; display: flex; flex-direction: column; gap: 4px; }
  code { background: var(--color-bg); padding: 1px 5px; border-radius: 4px; font-size: 0.85em; }
  input {
    font: inherit;
    color: inherit;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 46px;
  }
  .btn {
    min-height: 46px;
    padding: 0 16px;
    border-radius: var(--radius);
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    font-weight: 600;
  }
  .btn.primary { background: var(--color-accent); border-color: var(--color-accent); color: #fff; }
  .btn.ghost { background: transparent; }
  .btn.danger { background: #c0392b; border-color: #c0392b; color: #fff; }
  .btn:disabled { opacity: 0.5; }
</style>
