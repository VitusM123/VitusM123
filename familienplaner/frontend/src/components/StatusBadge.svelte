<script lang="ts">
  // Ersatz für die Statusanzeige der Kopfzeile, wenn diese ausgeblendet ist:
  // erscheint nur bei Problemen (Verbindung zum Pi weg, Sync-Fehler) bzw. während des Abgleichs.
  import { app } from '../lib/app.svelte';

  const label = $derived.by(() => {
    if (!app.connected) return 'Offline';
    if (app.sync?.state === 'error') return 'Sync-Fehler';
    if (app.sync?.state === 'running') return 'Synchronisiere …';
    return '';
  });
</script>

{#if label}
  <div class="badge" class:warn={label !== 'Synchronisiere …'} role="status">{label}</div>
{/if}

<style>
  .badge {
    position: fixed;
    bottom: calc(var(--tabbar-h) + 10px);   /* über der Tab-Leiste – verdeckt keine Bedienelemente */
    right: 12px;
    z-index: 50;
    padding: 4px 12px;
    border-radius: 14px;
    font-size: 0.8rem;
    background: var(--color-surface);
    color: var(--color-text-muted);
    border: 1px solid var(--color-border);
    pointer-events: none;
  }
  .badge.warn { color: #fff; background: #c0392b; border-color: #c0392b; font-weight: 600; }
</style>
