// Wendet ein Theme als CSS Custom Properties auf :root an (--color-<token>, --member-<n>, --font-*).
import type { Theme } from './types';

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  for (const [token, value] of Object.entries(theme.tokens)) {
    root.style.setProperty(`--color-${token}`, value);
  }
  theme.memberPalette.forEach((color, i) => root.style.setProperty(`--member-${i}`, color));
  root.style.setProperty('--font-family', `${theme.font.family}, system-ui, sans-serif`);
  root.style.setProperty('--font-scale', String(theme.font.scale));
  root.dataset.theme = theme.id;
  root.dataset.mode = theme.mode;
  root.style.colorScheme = theme.mode === 'dark' ? 'dark' : 'light';
}
