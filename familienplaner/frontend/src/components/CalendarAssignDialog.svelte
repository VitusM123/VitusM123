<script lang="ts">
  // „Wem gehören diese Kalender?“ – nach dem Verbinden eines Google-/iCloud-Kontos.
  import { api, ApiError } from '../lib/api';
  import { app } from '../lib/app.svelte';
  import type { CalendarInfo } from '../lib/types';
  import Modal from './Modal.svelte';

  let calendars = $state<CalendarInfo[]>([]);
  let selection = $state<Record<number, number[]>>({});
  let busy = $state(false);
  let loaded = $state(false);

  const account = $derived(app.assignAccountId);

  $effect(() => {
    if (account == null) return;
    loaded = false;
    void (async () => {
      app.calendars = await api.calendars();
      calendars = app.calendars.filter((c) => c.account_id === account);
      selection = Object.fromEntries(calendars.map((c) => [c.id, [...c.member_ids]]));
      loaded = true;
    })();
  });

  function toggle(calId: number, memberId: number) {
    const cur = selection[calId] ?? [];
    selection[calId] = cur.includes(memberId) ? cur.filter((m) => m !== memberId) : [...cur, memberId];
  }

  /** Schnellwahl: alle Kalender des Kontos gehören dieser Person */
  function allTo(memberId: number) {
    const everyone = calendars.every((c) => selection[c.id]?.includes(memberId));
    for (const c of calendars) {
      const cur = selection[c.id] ?? [];
      selection[c.id] = everyone ? cur.filter((m) => m !== memberId) : [...new Set([...cur, memberId])];
    }
  }

  async function save() {
    busy = true;
    try {
      for (const c of calendars) {
        const next = selection[c.id] ?? [];
        if (JSON.stringify([...next].sort()) !== JSON.stringify([...c.member_ids].sort())) {
          await api.updateCalendar(c.id, { member_ids: next });
        }
      }
      app.calendars = await api.calendars();
      app.eventsVersion++;
      app.notify('Zuordnung gespeichert');
      close();
    } catch (err) {
      app.notify(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen');
    } finally {
      busy = false;
    }
  }

  function close() {
    app.assignAccountId = null;
  }
</script>

{#if account != null}
  <Modal title="Wem gehören diese Kalender?" onclose={close} width="720px">
    {#if !loaded}
      <p class="muted">Kalender werden geladen …</p>
    {:else if calendars.length === 0}
      <p class="muted">Für dieses Konto wurden (noch) keine Kalender gefunden. Die Zuordnung ist später unter
        Einstellungen → Kalender möglich.</p>
    {:else if app.members.length === 0}
      <p class="muted">Lege zuerst Familienmitglieder an (Einstellungen → Familienmitglieder). Die Zuordnung ist danach
        unter Einstellungen → Kalender möglich.</p>
    {:else}
      <p class="muted">Termine aus diesen Kalendern erscheinen in der Familienansicht bei den gewählten Personen –
        außer ein Termin hat eine eigene Personenauswahl. Kalender ohne Person erscheinen unter „Alle“.</p>
      <div class="quick">
        <span>Alle Kalender gehören:</span>
        {#each app.members as m (m.id)}
          <button class="chip" style:--c={m.color}
            class:on={calendars.every((c) => selection[c.id]?.includes(m.id))}
            onclick={() => allTo(m.id)}>{m.avatar ? `${m.avatar} ` : ''}{m.name}</button>
        {/each}
      </div>
      <ul>
        {#each calendars as c (c.id)}
          <li>
            <div class="cal">
              <span class="dot" style:background={c.color ?? 'var(--color-accent)'}></span>
              <strong>{c.name}</strong>
              {#if c.read_only}<span class="badge">nur lesen</span>{/if}
            </div>
            <div class="chips">
              {#each app.members as m (m.id)}
                <button class="chip" style:--c={m.color} class:on={selection[c.id]?.includes(m.id)}
                  onclick={() => toggle(c.id, m.id)} aria-pressed={selection[c.id]?.includes(m.id)}>
                  {m.avatar ? `${m.avatar} ` : ''}{m.name}
                </button>
              {/each}
            </div>
          </li>
        {/each}
      </ul>
    {/if}
    {#snippet footer()}
      <button class="btn ghost" onclick={close}>Später</button>
      <button class="btn primary" onclick={save} disabled={busy || !loaded || !calendars.length || !app.members.length}>
        Speichern
      </button>
    {/snippet}
  </Modal>
{/if}

<style>
  .muted { color: var(--color-text-muted); margin-top: 0; }
  .quick {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    padding: 10px;
    background: var(--color-bg);
    border-radius: var(--radius);
    margin-bottom: 10px;
  }
  .quick span { color: var(--color-text-muted); margin-right: 4px; }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  li { padding: 10px 0; border-bottom: 1px solid var(--color-border); display: flex; flex-direction: column; gap: 8px; }
  .cal { display: flex; align-items: center; gap: 8px; }
  .dot { width: 14px; height: 14px; border-radius: 50%; }
  .badge { font-size: 0.75rem; color: var(--color-text-muted); border: 1px solid var(--color-border); border-radius: 10px; padding: 1px 8px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    min-height: 42px;
    padding: 0 14px;
    border-radius: 21px;
    border: 2px solid var(--c);
    background: var(--color-surface);
  }
  .chip.on { background: var(--c); color: #fff; font-weight: 600; }
  .btn { min-height: 48px; padding: 0 20px; border-radius: var(--radius); border: 1px solid var(--color-border); font-weight: 600; }
  .btn.primary { background: var(--color-accent); border-color: var(--color-accent); color: #fff; }
  .btn.ghost { background: transparent; }
  .btn:disabled { opacity: 0.5; }
</style>
