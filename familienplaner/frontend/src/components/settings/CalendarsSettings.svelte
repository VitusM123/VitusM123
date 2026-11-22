<script lang="ts">
  import { api, ApiError } from '../../lib/api';
  import { app } from '../../lib/app.svelte';
  import type { CalendarInfo } from '../../lib/types';

  const COLORS = ['#3E7CB1', '#E4572E', '#7FB069', '#F3A712', '#A06CD5', '#D1495B', '#00798C', '#616E7C'];
  const PROVIDER: Record<CalendarInfo['provider'], string> = { local: 'Lokal', google: 'Google', icloud: 'iCloud' };

  let newName = $state('');
  let adding = $state(false);
  let confirmDelete = $state<number | null>(null);

  async function update(cal: CalendarInfo, data: Partial<CalendarInfo>) {
    try {
      await api.updateCalendar(cal.id, data);
      app.calendars = await api.calendars();
    } catch (err) {
      app.notify(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen');
    }
  }

  async function add(e: SubmitEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    await api.createCalendar({ name: newName.trim(), color: COLORS[app.calendars.length % COLORS.length] });
    app.calendars = await api.calendars();
    newName = '';
    adding = false;
  }

  async function remove(id: number) {
    try {
      await api.deleteCalendar(id);
      app.calendars = await api.calendars();
    } catch (err) {
      app.notify(err instanceof ApiError ? err.message : 'Löschen fehlgeschlagen');
    }
    confirmDelete = null;
  }
</script>

<ul class="list">
  {#each app.calendars as cal (cal.id)}
    <li>
      <div class="top">
        <label class="vis">
          <input type="checkbox" checked={cal.visible} onchange={(e) => update(cal, { visible: e.currentTarget.checked })} />
          <span class="dot" style:background={cal.color ?? 'var(--color-accent)'}></span>
          <span class="name">{cal.name}</span>
        </label>
        <span class="badge">{PROVIDER[cal.provider]}{cal.read_only ? ' · nur lesen' : ''}</span>
        {#if cal.is_default}
          <span class="badge strong">Standard</span>
        {:else if !cal.read_only}
          <button class="small" onclick={() => update(cal, { is_default: true })}>Als Standard</button>
        {/if}
      </div>
      <div class="bottom">
        <div class="colors">
          {#each COLORS as c (c)}
            <button class="sw" class:on={c === cal.color} style:background={c} onclick={() => update(cal, { color: c })}
              aria-label="Farbe {c}"></button>
          {/each}
        </div>
        <label class="member">
          gehört zu
          <select
            value={cal.default_member_id ?? ''}
            onchange={(e) => update(cal, { default_member_id: e.currentTarget.value ? Number(e.currentTarget.value) : null })}
          >
            <option value="">– niemand –</option>
            {#each app.members as m (m.id)}<option value={m.id}>{m.name}</option>{/each}
          </select>
        </label>
        {#if cal.provider === 'local' && app.calendars.filter((c) => c.provider === 'local').length > 1}
          {#if confirmDelete === cal.id}
            <button class="small danger" onclick={() => remove(cal.id)}>Mit allen Terminen löschen</button>
          {:else}
            <button class="small ghost" onclick={() => (confirmDelete = cal.id)}>Löschen</button>
          {/if}
        {/if}
      </div>
    </li>
  {/each}
  <li>
    {#if adding}
      <form class="addform" onsubmit={add}>
        <input type="text" placeholder="Name des Kalenders" bind:value={newName} maxlength="100" />
        <button type="button" class="small" onclick={() => (adding = false)}>Abbrechen</button>
        <button type="submit" class="small primary">Anlegen</button>
      </form>
    {:else}
      <button class="add" onclick={() => (adding = true)}>+ Lokalen Kalender anlegen</button>
    {/if}
  </li>
</ul>
<p class="note">Neue Termine landen im Kalender mit der Markierung „Standard“. Nach dem Verbinden eines
  Google- oder iCloud-Kontos wird dessen Hauptkalender automatisch Standard, damit neue Termine auf allen Geräten
  erscheinen. Termine im lokalen Kalender „Familie“ bleiben nur auf dem Familienplaner.
  Google- und iCloud-Kalender erscheinen hier nach dem Verbinden eines Kontos. Schreibgeschützte Kalender
  (z. B. Feiertage) werden angezeigt, können aber nicht bearbeitet werden.</p>

<style>
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  li {
    padding: 10px 12px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .top, .bottom, .vis, .colors, .addform, .member { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .vis { flex: 1; min-height: 44px; }
  .vis input { width: 24px; height: 24px; }
  .dot { width: 14px; height: 14px; border-radius: 50%; }
  .name { font-weight: 600; }
  .badge { font-size: 0.75rem; color: var(--color-text-muted); border: 1px solid var(--color-border); border-radius: 10px; padding: 2px 8px; }
  .badge.strong { color: var(--color-accent); border-color: var(--color-accent); }
  .sw { width: 32px; height: 32px; border-radius: 50%; border: 3px solid transparent; }
  .sw.on { border-color: var(--color-text); }
  .member { color: var(--color-text-muted); margin-left: auto; }
  select, input[type='text'] {
    font: inherit;
    color: var(--color-text);
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 44px;
  }
  .addform input { flex: 1; }
  .small { min-height: 44px; padding: 0 14px; border-radius: 8px; border: 1px solid var(--color-border); }
  .primary { background: var(--color-accent); border-color: var(--color-accent); color: #fff; font-weight: 600; }
  .danger { background: #c0392b; border-color: #c0392b; color: #fff; }
  .ghost { color: #c0392b; border-color: #c0392b; }
  .add { min-height: 44px; text-align: left; color: var(--color-accent); font-weight: 600; }
  .note { color: var(--color-text-muted); font-size: 0.85rem; }
</style>
