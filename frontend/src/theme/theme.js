export const THEME_OPTIONS = ['light', 'dark', 'black', 'mint', 'cherry'];

export const THEME_PREFERENCE_KEY = 'fintech-theme-preference';

export const DEFAULT_THEME = 'light';

export function getStoredPreference() {
  try {
    const stored = window.localStorage.getItem(THEME_PREFERENCE_KEY);
    if (stored && THEME_OPTIONS.includes(stored)) {
      return stored;
    }
  } catch {
    return DEFAULT_THEME;
  }
  return DEFAULT_THEME;
}

export function applyTheme(resolvedTheme) {
  document.documentElement.setAttribute('data-theme', resolvedTheme);
}
