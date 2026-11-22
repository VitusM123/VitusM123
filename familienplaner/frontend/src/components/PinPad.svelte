<script lang="ts">
  // Zifferntastatur für die Admin-PIN (funktioniert ohne Bildschirmtastatur).
  interface Props {
    label: string;
    submitLabel?: string;
    onsubmit: (pin: string) => Promise<void> | void;
    error?: string | null;
  }
  let { label, submitLabel = 'OK', onsubmit, error = null }: Props = $props();
  let pin = $state('');
  let busy = $state(false);

  async function submit() {
    if (pin.length < 4 || busy) return;
    busy = true;
    try {
      await onsubmit(pin);
    } finally {
      pin = '';
      busy = false;
    }
  }
  const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '⌫', '0', '✓'];
  function press(k: string) {
    if (k === '⌫') pin = pin.slice(0, -1);
    else if (k === '✓') void submit();
    else if (pin.length < 12) pin += k;
  }
</script>

<div class="pinpad">
  <p class="label">{label}</p>
  <div class="dots" aria-live="polite">
    {#each { length: Math.max(4, pin.length) } as _, i}
      <span class:filled={i < pin.length}></span>
    {/each}
  </div>
  {#if error}<p class="error">{error}</p>{/if}
  <div class="keys">
    {#each keys as k (k)}
      <button
        class:ok={k === '✓'}
        disabled={busy || (k === '✓' && pin.length < 4)}
        onclick={() => press(k)}
        aria-label={k === '⌫' ? 'Löschen' : k === '✓' ? submitLabel : k}>{k}</button
      >
    {/each}
  </div>
</div>

<style>
  .pinpad { display: flex; flex-direction: column; align-items: center; gap: 12px; }
  .label { margin: 0; font-weight: 600; }
  .dots { display: flex; gap: 10px; min-height: 18px; }
  .dots span { width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--color-text-muted); }
  .dots span.filled { background: var(--color-text); border-color: var(--color-text); }
  .error { color: var(--color-accent); margin: 0; font-weight: 600; }
  .keys { display: grid; grid-template-columns: repeat(3, 72px); gap: 10px; }
  .keys button {
    height: 60px;
    border-radius: 12px;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    font-size: 1.4rem;
  }
  .keys button.ok { background: var(--color-accent); color: #fff; }
  .keys button:disabled { opacity: 0.4; }
</style>
