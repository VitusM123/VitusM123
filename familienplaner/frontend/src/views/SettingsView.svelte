<script lang="ts">
  import ThemePicker from '../components/ThemePicker.svelte';
  import { app } from '../lib/app.svelte';
</script>

<section>
  <h1>Einstellungen</h1>

  <h2>Farbschema</h2>
  <ThemePicker />

  <h2>Info</h2>
  <dl>
    <dt>Version</dt><dd>{app.info?.version ?? '–'}</dd>
    <dt>Zeitzone</dt><dd>{app.info?.timezone ?? '–'}</dd>
    <dt>Admin-PIN</dt><dd>{app.auth.pin_set ? 'gesetzt' : 'noch nicht gesetzt'}</dd>
  </dl>
  <!-- Familienmitglieder, Kalender, Konten, Display und Nachtmodus folgen in Schritt 2/3 -->
</section>

<style>
  h1 { margin-top: 0; }
  h2 { margin-top: 28px; font-size: 1.1rem; color: var(--color-text-muted); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; }
  dt { color: var(--color-text-muted); }
  dd { margin: 0; }
</style>
