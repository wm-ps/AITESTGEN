/**
 * Wires the `data-theme` attribute-setting mechanism (Story 1.2, Task 4) so
 * an in-app toggle can override the OS `prefers-color-scheme` — no visible
 * toggle control exists yet (Settings, where it would naturally live, was
 * cut), but the CSS-selector contract is established now to avoid
 * retrofitting it later.
 */

const STORAGE_KEY = 'theme'

export type Theme = 'light' | 'dark'

export function applyStoredTheme(): void {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') {
    document.documentElement.setAttribute('data-theme', stored)
  }
}

export function setTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem(STORAGE_KEY, theme)
}
