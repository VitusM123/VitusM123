<script lang="ts">
  // Software-Abdunklung für Displays ohne steuerbare Hintergrundbeleuchtung.
  // Berührung weckt den Bildschirm (POST /api/display/wake).
  import { api } from '../lib/api';
  import { app } from '../lib/app.svelte';

  async function wake() {
    app.display = await api.wake();
  }
</script>

{#if !app.display.screen_on}
  <button class="overlay" onclick={wake} aria-label="Bildschirm aufwecken"></button>
{:else if !app.display.hardware_backlight && app.display.brightness < 100}
  <div class="dim" style:opacity={(100 - app.display.brightness) / 100 * 0.85}></div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: #000;
    z-index: 1000;
    cursor: none;
  }
  .dim {
    position: fixed;
    inset: 0;
    background: #000;
    pointer-events: none;
    z-index: 999;
  }
</style>
