<script lang="ts">
  import { api, ApiError } from '../../lib/api';
  import { app } from '../../lib/app.svelte';
  import type { FamilyMember } from '../../lib/types';

  const EXTRA_COLORS = ['#E4572E', '#29335C', '#F3A712', '#669BBC', '#7FB069', '#A06CD5', '#D1495B', '#00798C', '#8D6A9F', '#2E4057'];
  const AVATARS = ['', '👩', '👨', '👧', '👦', '👶', '👵', '👴', '🧒', '🐶', '🐱', '⭐'];

  let editing = $state<number | 'new' | null>(null);
  let name = $state('');
  let color = $state(EXTRA_COLORS[0]);
  let avatar = $state('');
  let confirmDelete = $state<number | null>(null);
  let calendarIds = $state<number[]>([]);

  const calendarsOf = (memberId: number) => app.calendars.filter((c) => c.member_ids.includes(memberId));

  const palette = $derived([...new Set([...(app.theme?.memberPalette ?? []), ...EXTRA_COLORS])].filter((c) => /^#[0-9a-f]{6}$/i.test(c)));

  function start(m: FamilyMember | null) {
    editing = m ? m.id : 'new';
    name = m?.name ?? '';
    color = m?.color ?? palette[app.members.length % palette.length];
    avatar = m?.avatar ?? '';
    calendarIds = m ? calendarsOf(m.id).map((c) => c.id) : [];
    confirmDelete = null;
  }

  async function save(e: SubmitEvent) {
    e.preventDefault();
    if (!name.trim()) return app.notify('Bitte einen Namen eingeben');
    try {
      const data = { name: name.trim(), color, avatar: avatar || null };
      const member = editing === 'new' ? await api.createMember(data) : await api.updateMember(editing as number, data);
      const before = calendarsOf(member.id).map((c) => c.id).sort().join();
      if ([...calendarIds].sort().join() !== before) {
        await api.setMemberCalendars(member.id, calendarIds);
        app.calendars = await api.calendars();
      }
      app.members = await api.members();
      editing = null;
    } catch (err) {
      app.notify(err instanceof ApiError ? err.message : 'Speichern fehlgeschlagen');
    }
  }

  async function remove(id: number) {
    await api.deleteMember(id);
    app.members = await api.members();
    editing = null;
    confirmDelete = null;
  }

  async function move(index: number, dir: -1 | 1) {
    const ids = app.members.map((m) => m.id);
    const j = index + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[index], ids[j]] = [ids[j], ids[index]];
    app.members = await api.reorderMembers(ids);
  }
</script>

<ul class="list">
  {#each app.members as m, i (m.id)}
    <li>
      {#if editing === m.id}
        {@render form()}
      {:else}
        <span class="avatar" style:background={m.color}>{m.avatar || m.name.slice(0, 1)}</span>
        <span class="name">
          {m.name}
          <span class="cals">
            {#each calendarsOf(m.id) as c (c.id)}
              <span class="cal"><span class="dot" style:background={c.color ?? 'var(--color-accent)'}></span>{c.name}</span>
            {:else}
              <span class="none">keine eigenen Kalender</span>
            {/each}
          </span>
        </span>
        <button class="small" onclick={() => move(i, -1)} disabled={i === 0} aria-label="Nach oben">▲</button>
        <button class="small" onclick={() => move(i, 1)} disabled={i === app.members.length - 1} aria-label="Nach unten">▼</button>
        <button class="small" onclick={() => start(m)}>Bearbeiten</button>
      {/if}
    </li>
  {/each}
  <li>
    {#if editing === 'new'}
      {@render form()}
    {:else}
      <button class="add" onclick={() => start(null)}>+ Familienmitglied hinzufügen</button>
    {/if}
  </li>
</ul>

{#snippet form()}
  <form class="form" onsubmit={save}>
    <input type="text" placeholder="Name" bind:value={name} maxlength="60" />
    <div class="swatches" role="radiogroup" aria-label="Farbe">
      {#each palette as c (c)}
        <button type="button" class="sw" class:on={c === color} style:background={c} onclick={() => (color = c)}
          aria-label={c} aria-checked={c === color} role="radio"></button>
      {/each}
    </div>
    <div class="swatches" role="radiogroup" aria-label="Symbol">
      {#each AVATARS as a (a)}
        <button type="button" class="av" class:on={a === avatar} onclick={() => (avatar = a)} role="radio"
          aria-checked={a === avatar}>{a || name.slice(0, 1) || '–'}</button>
      {/each}
    </div>
    {#if app.calendars.length}
      <div class="calpick" role="group" aria-label="Kalender dieser Person">
        <span class="hint">Kalender:</span>
        {#each app.calendars as c (c.id)}
          <button type="button" class="calchip" class:on={calendarIds.includes(c.id)}
            aria-pressed={calendarIds.includes(c.id)}
            onclick={() => (calendarIds = calendarIds.includes(c.id)
              ? calendarIds.filter((x) => x !== c.id) : [...calendarIds, c.id])}>
            <span class="dot" style:background={c.color ?? 'var(--color-accent)'}></span>{c.name}
          </button>
        {/each}
      </div>
    {/if}
    <div class="row">
      {#if editing !== 'new' && editing !== null}
        {#if confirmDelete === editing}
          <span>Wirklich löschen?</span>
          <button type="button" class="small danger" onclick={() => remove(editing as number)}>Ja, löschen</button>
        {:else}
          <button type="button" class="small danger ghost" onclick={() => (confirmDelete = editing as number)}>Löschen</button>
        {/if}
      {/if}
      <span class="spacer"></span>
      <button type="button" class="small" onclick={() => (editing = null)}>Abbrechen</button>
      <button type="submit" class="small primary">Speichern</button>
    </div>
  </form>
{/snippet}

<style>
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  li {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
  }
  .avatar { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; color: #fff; font-size: 1.2rem; }
  .name { flex: 1; font-weight: 600; display: flex; flex-direction: column; gap: 2px; }
  .cals { display: flex; flex-wrap: wrap; gap: 4px 10px; font-weight: 400; font-size: 0.8rem; color: var(--color-text-muted); }
  .cal { display: inline-flex; align-items: center; gap: 4px; }
  .none { font-style: italic; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none; }
  .calpick { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .hint { color: var(--color-text-muted); margin-right: 4px; }
  .calchip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 40px;
    padding: 0 12px;
    border-radius: 20px;
    border: 1px solid var(--color-border);
    background: var(--color-bg);
  }
  .calchip.on { border-color: var(--color-accent); background: color-mix(in srgb, var(--color-accent) 18%, var(--color-surface)); font-weight: 600; }
  .form { display: flex; flex-direction: column; gap: 10px; width: 100%; }
  input {
    font: inherit;
    color: inherit;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 46px;
  }
  .swatches { display: flex; flex-wrap: wrap; gap: 8px; }
  .sw { width: 40px; height: 40px; border-radius: 50%; border: 3px solid transparent; }
  .sw.on { border-color: var(--color-text); }
  .av { width: 44px; height: 44px; border-radius: 10px; border: 2px solid var(--color-border); font-size: 1.3rem; }
  .av.on { border-color: var(--color-accent); background: var(--color-bg); }
  .row { display: flex; align-items: center; gap: 8px; }
  .spacer { flex: 1; }
  .small {
    min-height: 44px;
    min-width: 44px;
    padding: 0 14px;
    border-radius: 8px;
    border: 1px solid var(--color-border);
  }
  .small:disabled { opacity: 0.3; }
  .primary { background: var(--color-accent); border-color: var(--color-accent); color: #fff; font-weight: 600; }
  .danger { color: #c0392b; border-color: #c0392b; }
  .danger:not(.ghost) { background: #c0392b; color: #fff; }
  .add { width: 100%; min-height: 44px; text-align: left; color: var(--color-accent); font-weight: 600; }
</style>
