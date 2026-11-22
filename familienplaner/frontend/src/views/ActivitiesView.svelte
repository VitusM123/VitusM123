<script lang="ts">
  import { untrack } from 'svelte';
  import Modal from '../components/Modal.svelte';
  import { CATEGORIES, categoryInfo, RANGE_LABELS, rangeFor, type RangePreset } from '../lib/activities';
  import { api, ApiError } from '../lib/api';
  import { app } from '../lib/app.svelte';
  import { fmt, parseDate, sameDay } from '../lib/dates';
  import type { Activity, ActivityCategory, ActivitySearchResult } from '../lib/types';

  const RADII = [10, 25, 50, 100];

  let place = $state('');
  let radius = $state(25);
  let preset = $state<RangePreset>('weekend');
  let categories = $state<ActivityCategory[]>([]);
  let query = $state('');
  let result = $state<ActivitySearchResult | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);
  let expanded = $state<number | null>(null);

  // Dialog „Zum Kalender hinzufügen“
  let adding = $state<Activity | null>(null);
  let addMembers = $state<number[]>([]);
  let addCalendar = $state<number | null>(null);
  let addBusy = $state(false);

  const hasHome = $derived(app.settings?.home.lat != null);

  // Startwerte aus den Einstellungen übernehmen
  let initialized = false;
  $effect(() => {
    if (!initialized && app.settings) {
      radius = nearestRadius(app.settings.activity_radius_km);
      initialized = true;
    }
  });

  function nearestRadius(km: number): number {
    return RADII.reduce((best, r) => (Math.abs(r - km) < Math.abs(best - km) ? r : best), RADII[0]);
  }

  let lastKey = '';
  let lastVersion = -1;

  async function search(force = false) {
    const range = rangeFor(preset);
    const params = {
      address: place.trim() || null, radius_km: radius, date_from: range.from, date_to: range.to,
      categories: [...categories], query: query.trim() || null,
    };
    // Identische Anfrage (z. B. doppelt beim Laden) nicht erneut senden
    const key = JSON.stringify(params);
    if (!force && key === lastKey && lastVersion === app.activitiesVersion) return;
    lastKey = key;
    lastVersion = app.activitiesVersion;
    loading = true;
    error = null;
    try {
      result = await api.searchActivities(params);
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Suche fehlgeschlagen';
      result = null;
    } finally {
      loading = false;
    }
  }

  // Automatisch suchen bei geänderten Filtern und nach neuem Abruf der Quellen.
  // Ort und Suchbegriff lösen keine Suche pro Tastendruck aus (nur per „Suchen“).
  $effect(() => {
    void [radius, preset, categories.length, app.activitiesVersion, app.settings?.home.lat];
    if (app.settings) untrack(() => void search());
  });

  function toggleCategory(id: ActivityCategory) {
    categories = categories.includes(id) ? categories.filter((c) => c !== id) : [...categories, id];
  }

  function when(a: Activity): string {
    if (a.all_day) {
      const s = parseDate(a.start);
      const last = a.end ? new Date(parseDate(a.end).getTime() - 86_400_000) : s;
      return sameDay(s, last) ? 'ganztägig' : `bis ${fmt.dayMonth(last)}`;
    }
    return `${fmt.time(new Date(a.start))} Uhr`;
  }

  function dayOf(a: Activity): Date {
    return a.all_day ? parseDate(a.start) : new Date(a.start);
  }

  // Gruppierung nach Tag (mehrtägige Termine stehen am ersten Tag des Zeitraums)
  const groups = $derived.by(() => {
    if (!result) return [];
    const from = parseDate(rangeFor(preset).from);
    const map = new Map<string, { day: Date; items: Activity[] }>();
    for (const a of result.results) {
      let d = dayOf(a);
      if (d < from) d = from;
      const key = d.toDateString();
      if (!map.has(key)) map.set(key, { day: d, items: [] });
      map.get(key)!.items.push(a);
    }
    return [...map.values()].sort((x, y) => x.day.getTime() - y.day.getTime());
  });

  function openAdd(a: Activity) {
    adding = a;
    addMembers = [];
    addCalendar = (app.calendars.find((c) => c.is_default && !c.read_only) ?? app.writableCalendars[0])?.id ?? null;
  }

  async function confirmAdd() {
    if (!adding) return;
    addBusy = true;
    try {
      const ev = await api.addActivity(adding.id, { calendar_id: addCalendar, member_ids: addMembers });
      if (result) {
        result.results = result.results.map((r) => (r.id === adding!.id ? { ...r, event_id: ev.id } : r));
      }
      app.notify(`„${adding.title}“ wurde in den Kalender eingetragen`);
      adding = null;
    } catch (err) {
      app.notify(err instanceof ApiError ? err.message : 'Eintragen fehlgeschlagen');
    } finally {
      addBusy = false;
    }
  }

  function toggleMember(id: number) {
    addMembers = addMembers.includes(id) ? addMembers.filter((m) => m !== id) : [...addMembers, id];
  }
</script>

<div class="activities">
  <aside class="filters">
    <form onsubmit={(e) => { e.preventDefault(); void search(true); }}>
      <label class="lbl" for="place">Ort</label>
      <input id="place" type="text" bind:value={place} maxlength="200"
        placeholder={hasHome ? `Wohnort (${app.settings?.home.address || 'gespeichert'})` : 'Ort oder Adresse'} />

      <span class="lbl">Umkreis</span>
      <div class="chips">
        {#each RADII as r (r)}
          <button type="button" class="chip" class:on={radius === r} onclick={() => (radius = r)}>{r} km</button>
        {/each}
      </div>

      <span class="lbl">Zeitraum</span>
      <div class="chips">
        {#each Object.entries(RANGE_LABELS) as [key, label] (key)}
          <button type="button" class="chip" class:on={preset === key}
            onclick={() => (preset = key as RangePreset)}>{label}</button>
        {/each}
      </div>

      <span class="lbl">Was</span>
      <div class="chips">
        {#each CATEGORIES.filter((c) => c.id !== 'other') as c (c.id)}
          <button type="button" class="chip" class:on={categories.includes(c.id)} onclick={() => toggleCategory(c.id)}>
            {c.icon} {c.label}
          </button>
        {/each}
      </div>

      <label class="lbl" for="q">Suchbegriff</label>
      <input id="q" type="text" bind:value={query} maxlength="100" placeholder="z. B. Feuerwehr, Dinosaurier" />

      <button type="submit" class="search" disabled={loading}>{loading ? 'Suche …' : 'Suchen'}</button>
    </form>
  </aside>

  <section class="results" aria-busy={loading}>
    {#if error}
      <div class="hint">
        <p>{error}</p>
        {#if !hasHome}
          <button class="btn" onclick={() => app.navigate('settings')}>Wohnort in den Einstellungen festlegen</button>
        {/if}
      </div>
    {:else if result && result.total_in_db === 0}
      <div class="hint">
        <p>Noch keine Veranstaltungen geladen. Lege in den Einstellungen Veranstaltungsquellen an
          (z. B. den Veranstaltungskalender deiner Stadt als iCal-Feed).</p>
        <button class="btn" onclick={() => app.navigate('settings')}>Zu den Einstellungen</button>
      </div>
    {:else if result}
      <p class="summary">
        {result.results.length} Veranstaltung{result.results.length === 1 ? '' : 'en'} im Umkreis von {radius} km
        um {result.center.label}
      </p>
      {#if result.results.length === 0}
        <div class="hint"><p>Nichts gefunden. Größeren Umkreis, anderen Zeitraum oder weniger Filter probieren.</p></div>
      {/if}
      {#each groups as g (g.day.getTime())}
        <h2 class="day">{fmt.weekdayLong(g.day)}, {fmt.dayMonth(g.day)}</h2>
        {#each g.items as a (a.id)}
          {@const cat = categoryInfo(a.category)}
          <article class="card" class:open={expanded === a.id}>
            <button class="main" onclick={() => (expanded = expanded === a.id ? null : a.id)}>
              <span class="icon" aria-hidden="true">{cat.icon}</span>
              <span class="body">
                <span class="title">{a.title}</span>
                <span class="meta">
                  {when(a)}
                  {#if a.venue} · {a.venue}{/if}
                  {#if a.distance_km != null} · {a.distance_km < 1 ? 'unter 1 km' : `${a.distance_km.toLocaleString('de-DE')} km`}{/if}
                </span>
              </span>
              <span class="badge">{cat.label}</span>
            </button>
            {#if a.event_id}
              <span class="added">✓ Im Kalender</span>
            {:else}
              <button class="add" onclick={() => openAdd(a)}>+ Kalender</button>
            {/if}
            {#if expanded === a.id}
              <div class="details">
                {#if a.image_url}<img src={a.image_url} alt="" loading="lazy" />{/if}
                {#if a.description}<p>{a.description}</p>{/if}
                {#if a.address}<p class="muted">📍 {a.address}</p>{/if}
                {#if a.url}<p class="muted link">🔗 {a.url}</p>{/if}
                <p class="muted">Quelle: {a.source}</p>
              </div>
            {/if}
          </article>
        {/each}
      {/each}
    {/if}
  </section>
</div>

{#if adding}
  <Modal title="In den Kalender eintragen" onclose={() => (adding = null)} width="520px">
    <p class="add-title"><strong>{adding.title}</strong><br />
      <span class="muted">{fmt.full(dayOf(adding))} · {when(adding)}</span></p>
    {#if app.members.length}
      <p class="lbl">Wer geht hin?</p>
      <div class="chips">
        {#each app.members as m (m.id)}
          <button type="button" class="chip member" class:on={addMembers.includes(m.id)} style:--c={m.color}
            onclick={() => toggleMember(m.id)}>{m.avatar ? `${m.avatar} ` : ''}{m.name}</button>
        {/each}
      </div>
    {/if}
    {#if app.writableCalendars.length > 1}
      <p class="lbl">Kalender</p>
      <select bind:value={addCalendar}>
        {#each app.writableCalendars as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
      </select>
    {/if}
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (adding = null)}>Abbrechen</button>
      <button class="btn" onclick={confirmAdd} disabled={addBusy}>Eintragen</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .activities {
    height: 100%;
    display: grid;
    grid-template-columns: 330px 1fr;
    gap: 16px;
    min-height: 0;
  }
  .filters {
    overflow: auto;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    padding: 14px;
  }
  form { display: flex; flex-direction: column; gap: 8px; }
  .lbl { color: var(--color-text-muted); font-size: 0.8rem; font-weight: 600; text-transform: uppercase; margin-top: 6px; }
  input, select {
    font: inherit;
    color: inherit;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 46px;
    width: 100%;
  }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    min-height: 40px;
    padding: 0 12px;
    border-radius: 20px;
    border: 1px solid var(--color-border);
    background: var(--color-bg);
    font-size: 0.85rem;
  }
  .chip.on { background: var(--color-accent); border-color: var(--color-accent); color: #fff; font-weight: 600; }
  .chip.member { border: 2px solid var(--c); }
  .chip.member.on { background: var(--c); border-color: var(--c); }
  .search, .btn {
    min-height: 50px;
    border-radius: var(--radius);
    background: var(--color-accent);
    color: #fff;
    font-weight: 700;
    padding: 0 18px;
    margin-top: 8px;
  }
  .btn.ghost { background: transparent; color: var(--color-text); border: 1px solid var(--color-border); }
  .results { overflow: auto; min-height: 0; padding-bottom: 16px; }
  .summary { margin: 0 0 4px; color: var(--color-text-muted); }
  .day { font-size: 1rem; margin: 18px 0 8px; color: var(--color-text-muted); text-transform: capitalize; }
  .card {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    margin-bottom: 8px;
    overflow: hidden;
  }
  .main { display: flex; align-items: center; gap: 12px; padding: 10px 12px; text-align: left; min-height: 64px; }
  .icon { font-size: 1.6rem; width: 36px; text-align: center; flex: none; }
  .body { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .title { font-weight: 700; }
  .meta { color: var(--color-text-muted); font-size: 0.85rem; }
  .badge {
    font-size: 0.72rem;
    border: 1px solid var(--color-border);
    border-radius: 10px;
    padding: 2px 8px;
    color: var(--color-text-muted);
    white-space: nowrap;
  }
  .add, .added { margin-right: 12px; min-height: 44px; padding: 0 14px; border-radius: 8px; white-space: nowrap; }
  .add { background: var(--color-accent); color: #fff; font-weight: 600; }
  .added { display: inline-flex; align-items: center; color: var(--color-accent); font-weight: 600; }
  .details { grid-column: 1 / -1; padding: 0 16px 12px 60px; }
  .details img { max-width: 260px; border-radius: 8px; float: right; margin: 0 0 8px 12px; }
  .details p { margin: 6px 0; }
  .muted { color: var(--color-text-muted); font-size: 0.85rem; }
  .link { word-break: break-all; }
  .hint {
    padding: 24px;
    text-align: center;
    color: var(--color-text-muted);
    background: var(--color-surface);
    border: 1px dashed var(--color-border);
    border-radius: var(--radius);
  }
  .add-title { margin-top: 0; }
  @media (max-width: 800px) {
    .activities { grid-template-columns: 1fr; }
  }
</style>
