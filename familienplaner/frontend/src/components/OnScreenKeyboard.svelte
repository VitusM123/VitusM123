<script lang="ts">
  // Bildschirmtastatur (QWERTZ) für den Kiosk-Modus – Chromium in cage bringt keine eigene mit.
  // Erscheint beim Fokussieren von Textfeldern, fügt Zeichen an der Cursorposition ein und
  // löst ein input-Event aus, damit Svelte-Bindings aktualisiert werden.
  import { onMount } from 'svelte';

  type Field = HTMLInputElement | HTMLTextAreaElement;
  const TEXT_TYPES = new Set(['text', 'search', 'email', 'url', '']);

  let target = $state<Field | null>(null);
  let shift = $state(false);
  let symbols = $state(false);
  let el = $state<HTMLElement | null>(null);

  const letters = [
    ['q', 'w', 'e', 'r', 't', 'z', 'u', 'i', 'o', 'p', 'ü'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'ö', 'ä'],
    ['y', 'x', 'c', 'v', 'b', 'n', 'm', 'ß', '-', '.'],
  ];
  const symbolRows = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['@', '#', '&', '/', '(', ')', ':', ';', '"', "'", '€'],
    ['!', '?', ',', '+', '=', '%', '*', '_', '–', '.'],
  ];
  const rows = $derived(symbols ? symbolRows : letters);

  function isTextField(node: EventTarget | null): node is Field {
    if (node instanceof HTMLTextAreaElement) return !node.readOnly && !node.disabled;
    return node instanceof HTMLInputElement && TEXT_TYPES.has(node.type) && !node.readOnly && !node.disabled;
  }

  onMount(() => {
    const onFocusIn = (e: FocusEvent) => {
      if (isTextField(e.target)) {
        target = e.target;
        requestAnimationFrame(() => target?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
      }
    };
    const onFocusOut = (e: FocusEvent) => {
      // Fokus wandert auf ein anderes Element (nicht auf die Tastatur selbst) → schließen.
      // focusout kann mitten in einer DOM-Aktualisierung von Svelte feuern (Feld wird entfernt),
      // daher den Zustand erst danach ändern.
      const next = e.relatedTarget as Node | null;
      if (next && el?.contains(next)) return;
      if (isTextField(next)) return;
      queueMicrotask(() => {
        if (!isTextField(document.activeElement)) target = null;
      });
    };
    document.addEventListener('focusin', onFocusIn);
    document.addEventListener('focusout', onFocusOut);
    return () => {
      document.removeEventListener('focusin', onFocusIn);
      document.removeEventListener('focusout', onFocusOut);
    };
  });

  // Höhe als CSS-Variable bereitstellen, damit Dialoge darüber Platz lassen
  $effect(() => {
    const h = target && el ? el.offsetHeight : 0;
    document.documentElement.style.setProperty('--osk-h', `${h}px`);
  });

  function insert(text: string) {
    const f = target;
    if (!f) return;
    const start = f.selectionStart ?? f.value.length;
    const end = f.selectionEnd ?? f.value.length;
    if (f.maxLength > 0 && f.value.length - (end - start) + text.length > f.maxLength) return;
    f.setRangeText(text, start, end, 'end');
    f.dispatchEvent(new Event('input', { bubbles: true }));
    if (shift) shift = false;
  }

  function backspace() {
    const f = target;
    if (!f) return;
    const start = f.selectionStart ?? f.value.length;
    const end = f.selectionEnd ?? f.value.length;
    if (start === end && start === 0) return;
    f.setRangeText('', start === end ? start - 1 : start, end, 'end');
    f.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function enter() {
    const f = target;
    if (!f) return;
    if (f instanceof HTMLTextAreaElement) return insert('\n');
    f.form?.requestSubmit();
    f.blur();
    target = null;
  }

  function close() {
    target?.blur();
    target = null;
  }

  // Fokus im Textfeld behalten: Tastendruck darf den Fokus nicht stehlen
  const keep = (e: Event) => e.preventDefault();
</script>

{#if target}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions (verhindert nur Fokusverlust) -->
  <div class="osk" bind:this={el} onpointerdown={keep} onmousedown={keep} role="group" aria-label="Bildschirmtastatur">
    {#each rows as row, i (i)}
      <div class="row">
        {#if i === 2 && !symbols}
          <button class="wide" class:on={shift} onclick={() => (shift = !shift)} aria-label="Umschalt">⇧</button>
        {/if}
        {#each row as key (key)}
          <button onclick={() => insert(shift ? key.toUpperCase() : key)}>{shift ? key.toUpperCase() : key}</button>
        {/each}
        {#if i === 2}
          <button class="wide" onclick={backspace} aria-label="Löschen">⌫</button>
        {/if}
      </div>
    {/each}
    <div class="row">
      <button class="wide" onclick={() => (symbols = !symbols)}>{symbols ? 'ABC' : '?123'}</button>
      <button class="space" onclick={() => insert(' ')} aria-label="Leerzeichen"></button>
      <button class="wide" onclick={enter}>{target instanceof HTMLTextAreaElement ? '↵' : 'Fertig'}</button>
      <button class="wide" onclick={close} aria-label="Tastatur schließen">⌄</button>
    </div>
  </div>
{/if}

<style>
  .osk {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 500;
    background: var(--color-surface);
    border-top: 1px solid var(--color-border);
    box-shadow: 0 -6px 24px rgba(0, 0, 0, 0.2);
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    touch-action: manipulation;
  }
  .row { display: flex; justify-content: center; gap: 6px; }
  button {
    flex: 0 1 84px;
    height: 54px;
    border-radius: 8px;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    font-size: 1.25rem;
  }
  button:active { background: var(--color-border); }
  .wide { flex-basis: 110px; font-size: 1rem; }
  .on { background: var(--color-accent); color: #fff; }
  .space { flex: 1 1 400px; max-width: 520px; }
</style>
