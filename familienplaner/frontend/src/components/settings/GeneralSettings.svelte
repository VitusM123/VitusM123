<script lang="ts">
  import { api, ApiError } from '../../lib/api';
  import { app } from '../../lib/app.svelte';
  import type { UserSettings } from '../../lib/types';

  async function update(data: Partial<UserSettings>) {
    try {
      app.settings = await api.updateSettings(data);
      app.setTheme(await api.activeTheme());
    } catch (err) {
      app.notify(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen');
    }
  }
  const s = $derived(app.settings!);
  const lcdThemes = $derived(app.themes.filter((t) => t.mode !== 'eink'));
</script>

{#if app.settings}
  <div class="grid">
    <label for="dv">Startansicht</label>
    <select id="dv" value={s.default_view} onchange={(e) => update({ default_view: e.currentTarget.value as UserSettings['default_view'] })}>
      <option value="week">Woche</option>
      <option value="month">Monat</option>
      <option value="family">Familie</option>
    </select>

    <label for="ws">Woche beginnt am</label>
    <select id="ws" value={s.week_starts_on} onchange={(e) => update({ week_starts_on: e.currentTarget.value as 'monday' | 'sunday' })}>
      <option value="monday">Montag</option>
      <option value="sunday">Sonntag</option>
    </select>

    <span>Kopfzeile</span>
    <label class="check">
      <input type="checkbox" checked={s.show_header} onchange={(e) => update({ show_header: e.currentTarget.checked })} />
      Uhrzeit und Datum oben anzeigen
    </label>

    <span>Nachtmodus</span>
    <div class="inline">
      <label class="check">
        <input type="checkbox" checked={s.night_mode.enabled}
          onchange={(e) => update({ night_mode: { ...s.night_mode, enabled: e.currentTarget.checked } })} />
        Bildschirm nachts aus
      </label>
      <input type="time" value={s.night_mode.off} aria-label="Aus um"
        onchange={(e) => update({ night_mode: { ...s.night_mode, off: e.currentTarget.value } })} />
      bis
      <input type="time" value={s.night_mode.on} aria-label="An um"
        onchange={(e) => update({ night_mode: { ...s.night_mode, on: e.currentTarget.value } })} />
    </div>

    <span>Automatisches Farbschema</span>
    <div class="inline">
      <label class="check">
        <input type="checkbox" checked={s.auto_theme} onchange={(e) => update({ auto_theme: e.currentTarget.checked })} />
        Tag/Nacht wechseln
      </label>
      {#if s.auto_theme}
        <select value={s.day_theme} aria-label="Tag-Theme" onchange={(e) => update({ day_theme: e.currentTarget.value })}>
          {#each lcdThemes as t (t.id)}<option value={t.id}>{t.name}</option>{/each}
        </select>
        ab
        <input type="time" value={s.day_starts} onchange={(e) => update({ day_starts: e.currentTarget.value })} />
        <select value={s.night_theme} aria-label="Nacht-Theme" onchange={(e) => update({ night_theme: e.currentTarget.value })}>
          {#each lcdThemes as t (t.id)}<option value={t.id}>{t.name}</option>{/each}
        </select>
        ab
        <input type="time" value={s.night_starts} onchange={(e) => update({ night_starts: e.currentTarget.value })} />
      {/if}
    </div>
  </div>
{/if}

<style>
  .grid { display: grid; grid-template-columns: 220px 1fr; gap: 12px 16px; align-items: center; }
  label, span { color: var(--color-text-muted); }
  .inline { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: var(--color-text-muted); }
  .check { display: flex; align-items: center; gap: 8px; color: var(--color-text); min-height: 44px; }
  .check input { width: 24px; height: 24px; }
  select, input[type='time'] {
    font: inherit;
    color: var(--color-text);
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 44px;
  }
  select { justify-self: start; }
</style>
