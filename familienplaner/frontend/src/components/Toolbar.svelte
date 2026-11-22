<script lang="ts">
  import type { Snippet } from 'svelte';
  import { app } from '../lib/app.svelte';

  interface Props {
    title: string;
    onprev: () => void;
    onnext: () => void;
    ontoday: () => void;
    showFilter?: boolean;
    actions?: Snippet;
  }
  let { title, onprev, onnext, ontoday, showFilter = true, actions }: Props = $props();
</script>

<div class="toolbar">
  <div class="nav">
    <button class="icon" onclick={onprev} aria-label="Zurück">‹</button>
    <button class="today" onclick={ontoday}>Heute</button>
    <button class="icon" onclick={onnext} aria-label="Weiter">›</button>
    <h1>{title}</h1>
  </div>
  <div class="right">
    {#if showFilter && app.members.length > 1}
      <div class="filter" role="group" aria-label="Nach Person filtern">
        {#each app.members as m (m.id)}
          <button
            class="member"
            class:on={app.memberFilter.includes(m.id)}
            class:dim={app.memberFilter.length > 0 && !app.memberFilter.includes(m.id)}
            style:--c={m.color}
            onclick={() => app.toggleMemberFilter(m.id)}
            aria-pressed={app.memberFilter.includes(m.id)}
          >
            {m.avatar ?? m.name.slice(0, 1)}
            <span class="name">{m.name}</span>
          </button>
        {/each}
      </div>
    {/if}
    {@render actions?.()}
  </div>
</div>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }
  .nav, .right, .filter { display: flex; align-items: center; gap: 8px; }
  h1 { font-size: 1.35rem; margin: 0 0 0 8px; white-space: nowrap; }
  button.icon, button.today {
    min-width: 48px;
    height: 48px;
    border-radius: var(--radius);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
  }
  button.icon { font-size: 1.8rem; line-height: 1; }
  button.today { padding: 0 16px; font-weight: 600; }
  .member {
    height: 44px;
    padding: 0 12px 0 10px;
    border-radius: 22px;
    border: 2px solid var(--c);
    background: var(--color-surface);
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .member.on { background: var(--c); color: #fff; }
  .member.dim { opacity: 0.45; }
  .name { font-size: 0.85rem; }
</style>
