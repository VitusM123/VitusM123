// Svelte-Action: horizontales Wischen (Touch/Maus) → vorherige/nächste Periode.
export function swipe(node: HTMLElement, handlers: { left: () => void; right: () => void }) {
  let x0 = 0;
  let y0 = 0;
  let t0 = 0;
  let active = false;
  const down = (e: PointerEvent) => {
    if (e.pointerType === 'mouse') return;   // Maus nutzt die Pfeiltasten
    x0 = e.clientX; y0 = e.clientY; t0 = Date.now(); active = true;
  };
  const up = (e: PointerEvent) => {
    if (!active) return;
    active = false;
    const dx = e.clientX - x0;
    const dy = e.clientY - y0;
    if (Date.now() - t0 < 600 && Math.abs(dx) > 70 && Math.abs(dy) < Math.abs(dx) * 0.6) {
      (dx < 0 ? handlers.left : handlers.right)();
    }
  };
  const cancel = () => (active = false);
  // Horizontale Gesten selbst auswerten, vertikales Scrollen bleibt dem Browser überlassen
  node.style.touchAction = 'pan-y';
  node.addEventListener('pointerdown', down);
  node.addEventListener('pointerup', up);
  node.addEventListener('pointercancel', cancel);
  return {
    update(h: typeof handlers) { handlers = h; },
    destroy() {
      node.removeEventListener('pointerdown', down);
      node.removeEventListener('pointerup', up);
      node.removeEventListener('pointercancel', cancel);
    },
  };
}
