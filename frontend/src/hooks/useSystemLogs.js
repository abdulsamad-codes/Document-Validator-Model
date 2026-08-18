import { useCallback, useEffect, useRef, useState } from 'react';

import { searchSystemLogs } from '../services/systemLogs';
import { getApiErrorMessage } from '../utils/apiError';

const DEFAULT_FILTERS = {
  applicationId: '',
  actor: '',
  eventType: '',
  severity: '',
  dateFrom: '',
  dateTo: '',
  query: '',
};

/**
 * Load and search the IT system log.
 *
 * Filters are applied server-side (newest first); every filter change triggers
 * a fresh search. A request-id guard discards out-of-order responses so a stale
 * search can never overwrite a newer one.
 *
 * @returns {object} Log entries, pagination, filter state and search callbacks.
 */
export function useSystemLogs() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Guards against out-of-order responses: overlapping searches (StrictMode
  // double-effects, rapid filter changes) must not let a stale response
  // overwrite the latest one.
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await searchSystemLogs(
        {
          applicationId: filters.applicationId || undefined,
          actor: filters.actor || undefined,
          eventType: filters.eventType || undefined,
          severity: filters.severity || undefined,
          dateFrom: filters.dateFrom || undefined,
          dateTo: filters.dateTo || undefined,
          query: filters.query || undefined,
        },
        { limit: 100 }
      );
      if (requestId === requestIdRef.current) {
        setEntries(data?.items ?? []);
        setTotal(data?.total ?? 0);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(getApiErrorMessage(err));
        setEntries([]);
        setTotal(0);
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [filters]);

  useEffect(() => {
    // Fetch-on-mount/filter-change via a memoized hook function -- see
    // AuthProvider.jsx or the full-stack audit (Phase 8) for why this
    // react-hooks/set-state-in-effect suppression is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const setFilter = useCallback((key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleReset = useCallback(() => {
    setFilters(DEFAULT_FILTERS);
  }, []);

  return {
    entries,
    total,
    loading,
    error,
    filters,
    onFilterChange: setFilter,
    onReset: handleReset,
    onSearch: load,
  };
}