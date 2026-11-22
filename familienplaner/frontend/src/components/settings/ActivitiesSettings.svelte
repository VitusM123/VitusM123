<script lang="ts">
  import { api, ApiError } from '../../lib/api';
  import { app } from '../../lib/app.svelte';
  import type { ActivitySourceInfo, ActivitySourceType } from '../../lib/types';

  const TYPES: { id: ActivitySourceType; label: string; hint: string }[] = [
    { id: 'ical', label: 'iCal-Feed', hint: 'Veranstaltungskalender von Stadt, Museum, Messe, Hochschule (Adresse endet oft auf .ics)' },
    { id: 'rss', label: 'RSS-Feed', hint: 'Veranstaltungs-Newsfeed; Termine werden aus Titel/Text erkannt' },
    { id: 'ticketmaster', label: 'Ticketmaster', hint: 'Konzerte, Shows, Familie – kostenloser API-Schlüssel auf developer.ticketmaster.com' },
    { id: 'scraper', label: 'Webseite', hint: 'Seite ohne Feed per CSS-Selektoren auslesen (für Fortgeschrittene)' },
  ];
  const SCRAPER_FIELDS = [
    ['item', 'Element je Veranstaltung', '.event'], ['title', 'Titel', 'h3'], ['date', 'Datum/Uhrzeit', '.date'],
    ['link', 'Link (optional)', 'a'], ['location', 'Ort (optional)', '.ort'],
  ] as const;

  let sources = $state<ActivitySourceInfo[]>([]);
  let homeAddress = $state('');
  let busy = $state(false);
  let adding = $state(false);
  let type = $state<ActivitySourceType>('ical');
  let name = $state('');
  let config = $state<Record<string, string>>({});
  let testResult = $state<{ count: number; sample: { title: string; start: string }[] } | null>(null);
  let formError = $state<string | null>(null);
  let confirmDelete = $state<number | null>(null);

  async function load() {
    sources = await api.activitySources();
  }
  $effect(() => {
    void app.activitiesVersion;
    void load();
  });
  $effect(() => {
    homeAddress = app.settings?.home.address ?? '';
  });

  async function saveHome(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    try {
      const geo = await api.geocode(homeAddress);
      app.settings = await api.updateSettings({ home: { address: homeAddress.trim(), lat: geo.lat, lon: geo.lon } });
      app.notify(`Wohnort gespeichert (${geo.lat.toFixed(3)}, ${geo.lon.toFixed(3)})`);
    } catch (err) {
      app.notify(err instanceof ApiError ? err.message : 'Ort nicht gefunden');
    } finally {
      busy = false;
    }
  }

  async function setRadius(km: number) {
    app.settings = await api.updateSettings({ activity_radius_km: km });
  }

  function startAdd() {
    adding = true;
    type = 'ical';
    name = '';
    config = {};
    testResult = null;
    formError = null;
  }

  const payload = () => ({ type, name: name.trim() || TYPES.find((t) => t.id === type)!.label, config });

  async function test() {
    busy = true;
    formError = null;
    try {
      testResult = await api.testActivitySource(payload());
    } catch (err) {
      formError = err instanceof ApiError ? err.message : 'Test fehlgeschlagen';
      testResult = null;
    } finally {
      busy = false;
    }
  }

  async function save(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    formError = null;
    try {
      const src = await api.createActivitySource(payload());
      adding = false;
      app.notify(src.last_error ? `Gespeichert, aber: ${src.last_error}` : `${src.last_count} Veranstaltungen geladen`);
      await load();
      app.activitiesVersion++;
    } catch (err) {
      formError = err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen';
    } finally {
      busy = false;
    }
  }

  async function toggle(s: ActivitySourceInfo) {
    await api.updateActivitySource(s.id, { enabled: !s.enabled });
    await load();
    app.activitiesVersion++;
  }

  async function remove(id: number) {
    await api.deleteActivitySource(id);
    confirmDelete = null;
    await load();
    app.activitiesVersion++;
  }

  async function refresh() {
    busy = true;
    try {
      const res = await api.refreshActivities();
      const total = res.reduce((n, r) => n + r.count, 0);
      const failed = res.filter((r) => r.error).length;
      app.notify(`${total} Veranstaltungen aktualisiert${failed ? ` · ${failed} Quelle(n) mit Fehler` : ''}`);
      await load();
    } finally {
      busy = false;
    }
  }

  function ago(iso: string | null): string {
    if (!iso) return 'noch nie';
    return new Date(iso).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
  }
</script>

<form class="row home" onsubmit={saveHome}>
  <label for="home">Wohnort</label>
  <input id="home" type="text" bind:value={homeAddress} placeholder="z. B. Musterstraße 1, 80331 München" maxlength="200" />
  <button type="submit" class="btn primary" disabled={busy || homeAddress.trim().length < 3}>Ort suchen & speichern</button>
</form>
{#if app.settings?.home.lat != null}
  <p class="muted">Gespeichert: {app.settings.home.lat.toFixed(4)}, {app.settings.home.lon?.toFixed(4)} ·
    Ortsdaten © OpenStreetMap-Mitwirkende</p>
{/if}
<div class="row">
  <span class="label">Standard-Umkreis</span>
  {#each [10, 25, 50, 100] as km (km)}
    <button class="chip" class:on={app.settings?.activity_radius_km === km} onclick={() => setRadius(km)}>{km} km</button>
  {/each}
</div>

<h3>Veranstaltungsquellen</h3>
<ul class="list">
  {#each sources as s (s.id)}
    <li class:off={!s.enabled}>
      <div class="info">
        <strong>{s.name}</strong>
        <span class="muted">{TYPES.find((t) => t.id === s.type)?.label} · {s.last_count} Veranstaltungen ·
          abgerufen {ago(s.last_fetch)}</span>
        {#if s.config.url}<span class="muted url">{s.config.url}</span>{/if}
        {#if s.last_error}<span class="err">⚠ {s.last_error}</span>{/if}
      </div>
      <div class="actions">
        <button class="btn" onclick={() => toggle(s)}>{s.enabled ? 'Pausieren' : 'Aktivieren'}</button>
        {#if confirmDelete === s.id}
          <button class="btn danger" onclick={() => remove(s.id)}>Löschen bestätigen</button>
        {:else}
          <button class="btn ghost" onclick={() => (confirmDelete = s.id)}>Löschen</button>
        {/if}
      </div>
    </li>
  {/each}
</ul>

{#if adding}
  <form class="box" onsubmit={save}>
    <div class="types">
      {#each TYPES as t (t.id)}
        <button type="button" class="chip" class:on={type === t.id}
          onclick={() => { type = t.id; config = {}; testResult = null; }}>{t.label}</button>
      {/each}
    </div>
    <p class="muted">{TYPES.find((t) => t.id === type)?.hint}</p>
    <input type="text" placeholder="Name (z. B. Stadt München)" bind:value={name} maxlength="100" />
    {#if type === 'ticketmaster'}
      <input type="password" placeholder="API-Schlüssel (Consumer Key)" bind:value={config.api_key} autocomplete="off" />
    {:else}
      <input type="text" placeholder={type === 'scraper' ? 'Adresse der Veranstaltungsseite' : 'Feed-Adresse (https://… oder webcal://…)'}
        bind:value={config.url} />
    {/if}
    {#if type === 'scraper'}
      <div class="grid">
        {#each SCRAPER_FIELDS as [key, label, example] (key)}
          <label for={`sc-${key}`}>{label}</label>
          <input id={`sc-${key}`} type="text" placeholder={example} bind:value={config[key]} />
        {/each}
      </div>
    {/if}
    {#if formError}<p class="err" role="alert">⚠ {formError}</p>{/if}
    {#if testResult}
      <div class="test">
        <strong>{testResult.count} Veranstaltungen gefunden</strong>
        <ul>
          {#each testResult.sample as s, i (i)}
            <li>{new Date(s.start).toLocaleDateString('de-DE')} – {s.title}</li>
          {/each}
        </ul>
      </div>
    {/if}
    <div class="row">
      <button type="button" class="btn ghost" onclick={() => (adding = false)}>Abbrechen</button>
      <button type="button" class="btn" onclick={test} disabled={busy}>Testen</button>
      <button type="submit" class="btn primary" disabled={busy}>Speichern</button>
    </div>
  </form>
{:else}
  <div class="row">
    <button class="btn primary" onclick={startAdd}>+ Quelle hinzufügen</button>
    {#if sources.length}<button class="btn" onclick={refresh} disabled={busy}>Jetzt aktualisieren</button>{/if}
  </div>
{/if}

<style>
  h3 { margin: 20px 0 8px; font-size: 1rem; }
  .row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
  .home input { flex: 1; min-width: 240px; }
  .label, label { color: var(--color-text-muted); }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    padding: 10px 12px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
  }
  li.off { opacity: 0.6; }
  .info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
  .url { word-break: break-all; }
  .actions { display: flex; gap: 6px; }
  .muted { color: var(--color-text-muted); font-size: 0.85rem; }
  .err { color: #c0392b; font-weight: 600; font-size: 0.85rem; margin: 0; }
  .box {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px 14px;
    margin-top: 8px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
  }
  .box p { margin: 0; }
  .types { display: flex; gap: 6px; flex-wrap: wrap; }
  .grid { display: grid; grid-template-columns: 200px 1fr; gap: 8px; align-items: center; }
  .test { background: var(--color-bg); border-radius: 8px; padding: 8px 12px; }
  .test ul { margin: 6px 0 0; padding-left: 18px; font-size: 0.85rem; }
  input {
    font: inherit;
    color: inherit;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 46px;
  }
  .chip {
    min-height: 42px;
    padding: 0 14px;
    border-radius: 21px;
    border: 1px solid var(--color-border);
    background: var(--color-bg);
  }
  .chip.on { background: var(--color-accent); border-color: var(--color-accent); color: #fff; font-weight: 600; }
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
