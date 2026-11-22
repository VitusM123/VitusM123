<script lang="ts">
  // App-Shell: Navigation (Monat | Woche | Familie | Aktivitäten | Einstellungen),
  // Hash-Routing, Theme-Provider, WebSocket-Anbindung.
  // TODO: Router + Views einbinden
</script>

<main class="shell">
  <!-- TODO: <Header/>, aktive View, <TabBar/> -->
</main>

<style>
  :global(:root) {
    --color-bg: #f5f7fa;
    --color-surface: #ffffff;
    --color-text: #1f2933;
  }
  .shell {
    min-height: 100vh;
    background: var(--color-bg);
    color: var(--color-text);
  }
</style>
