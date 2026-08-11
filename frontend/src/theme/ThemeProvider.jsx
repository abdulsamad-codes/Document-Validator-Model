import { createContext, useCallback, useEffect, useMemo, useState } from 'react';

import {
  applyTheme,
  getStoredPreference,
  getSystemTheme,
  resolveTheme,
} from './theme';

export const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [preference, setPreference] = useState(getStoredPreference);
  const [systemTheme, setSystemTheme] = useState(getSystemTheme);

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => setSystemTheme(media.matches ? 'dark' : 'light');
    media.addEventListener('change', handleChange);
    return () => media.removeEventListener('change', handleChange);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem('fintech-theme-preference', preference);
    } catch {
      // Ignore storage failures (private mode, disabled storage).
    }
    applyTheme(resolveTheme(preference));
  }, [preference, systemTheme]);

  const setTheme = useCallback((next) => {
    setPreference(next);
  }, []);

  const value = useMemo(
    () => ({
      theme: preference,
      resolvedTheme: preference === 'system' ? systemTheme : preference,
      setTheme,
    }),
    [preference, systemTheme, setTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
