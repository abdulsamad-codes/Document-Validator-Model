export const THEME_OPTIONS = ['light', 'dark', 'system'];

export const THEME_PREFERENCE_KEY = 'fintech-theme-preference';

export function getStoredPreference() {
  try {
    const stored = window.localStorage.getItem(THEME_PREFERENCE_KEY);
    if (stored && THEME_OPTIONS.includes(stored)) {
      return stored;
    }
  } catch {
    return 'system';
  }
  return 'system';
}

export function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function resolveTheme(preference) {
  return preference === 'system' ? getSystemTheme() : preference;
}

export function applyTheme(resolvedTheme) {
  document.documentElement.setAttribute('data-theme', resolvedTheme);
}
