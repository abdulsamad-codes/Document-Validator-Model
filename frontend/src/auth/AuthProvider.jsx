import { useCallback, useEffect, useMemo, useState } from 'react';

import * as authService from './authService';
import { AuthContext } from './AuthContext';
import { abortPendingRequests, setUnauthorizedHandler } from '../services/api';

function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  const resetSession = useCallback(() => {
    setUser(null);
    setAuthenticated(false);
  }, []);

  const checkAuthentication = useCallback(async () => {
    setLoading(true);
    try {
      const data = await authService.getCurrentUser();
      setUser(data?.user ?? data ?? null);
      setAuthenticated(true);
    } catch {
      resetSession();
    } finally {
      setLoading(false);
    }
  }, [resetSession]);

  const login = useCallback(async (credentials) => {
    await authService.login(credentials);
    const data = await authService.getCurrentUser();
    setUser(data?.user ?? data ?? null);
    setAuthenticated(true);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } catch {
      // Best effort: the local session is cleared regardless.
    }
    abortPendingRequests();
    resetSession();
  }, [resetSession]);

  const refreshSession = useCallback(() => authService.refreshSession(), []);

  useEffect(() => {
    checkAuthentication();
  }, [checkAuthentication]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      abortPendingRequests();
      resetSession();
    });
    return () => setUnauthorizedHandler(null);
  }, [resetSession]);

  const value = useMemo(
    () => ({
      user,
      authenticated,
      loading,
      login,
      logout,
      refreshSession,
      checkAuthentication,
    }),
    [user, authenticated, loading, login, logout, refreshSession, checkAuthentication]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export default AuthProvider;
