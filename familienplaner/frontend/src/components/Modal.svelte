<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    onclose: () => void;
    children: Snippet;
    footer?: Snippet;
    width?: string;
  }
  let { title, onclose, children, footer, width = '640px' }: Props = $props();

  function onkey(e: KeyboardEvent) {
    if (e.key === 'Escape') onclose();
  }
</script>

<svelte:window onkeydown={onkey} />

<div class="backdrop" onpointerdown={(e) => e.target === e.currentTarget && onclose()} role="presentation">
  <div class="panel" role="dialog" aria-modal="true" aria-label={title} style:max-width={width}>
    <header>
      <h2>{title}</h2>
      <button class="close" onclick={onclose} aria-label="Schließen">✕</button>
    </header>
    <div class="body">{@render children()}</div>
    {#if footer}<footer>{@render footer()}</footer>{/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 24px 16px calc(24px + var(--osk-h, 0px));
    z-index: 100;
    overflow: auto;
  }
  .panel {
    width: 100%;
    background: var(--color-surface);
    color: var(--color-text);
    border-radius: 14px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    display: flex;
    flex-direction: column;
    max-height: calc(100vh - 48px - var(--osk-h, 0px));
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid var(--color-border);
  }
  h2 { margin: 0; font-size: 1.2rem; }
  .close { width: 44px; height: 44px; font-size: 1.2rem; border-radius: 50%; }
  .body { padding: 16px 18px; overflow: auto; }
  footer {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
    padding: 12px 18px;
    border-top: 1px solid var(--color-border);
    flex-wrap: wrap;
  }
</style>
