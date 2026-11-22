<script lang="ts">
  import { app } from '../lib/app.svelte';

  let busy = $state(false);

  async function choose(id: string) {
    busy = true;
    try {
      await app.selectTheme(id);
    } finally {
      busy = false;
    }
  }
</script>

<div class="grid" aria-busy={busy}>
  {#each app.themes as theme (theme.id)}
    <button
      class="swatch"
      class:selected={app.theme?.id === theme.id}
      style:background={theme.tokens.bg}
      style:color={theme.tokens.text}
      style:border-color={app.theme?.id === theme.id ? theme.tokens.accent : theme.tokens.border}
      onclick={() => choose(theme.id)}
      disabled={busy}
    >
      <span class="name">{theme.name}</span>
      <span class="chips">
        <span style:background={theme.tokens.surface}></span>
        <span style:background={theme.tokens.accent}></span>
        <span style:background={theme.tokens.today}></span>
        {#each theme.memberPalette.slice(0, 4) as color}
          <span style:background={color}></span>
        {/each}
      </span>
    </button>
  {/each}
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 12px;
  }
  .swatch {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
    padding: 14px;
    border: 3px solid;
    border-radius: var(--radius);
    text-align: left;
  }
  .swatch.selected { font-weight: 700; }
  .chips { display: flex; gap: 4px; }
  .chips span {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 1px solid rgba(0, 0, 0, 0.15);
  }
</style>
