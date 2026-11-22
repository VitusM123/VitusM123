<script lang="ts">
  import { app } from '../lib/app.svelte';
</script>

{#if app.toast}
  <div class="toast" role="status">{app.toast}</div>
{/if}

<style>
  .toast {
    position: fixed;
    left: 50%;
    bottom: calc(var(--tabbar-h) + 16px + var(--osk-h, 0px));
    transform: translateX(-50%);
    background: var(--color-text);
    color: var(--color-surface);
    padding: 12px 20px;
    border-radius: 24px;
    z-index: 300;
    max-width: 90vw;
  }
</style>
