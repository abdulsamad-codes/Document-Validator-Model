import { useCallback, useEffect, useState } from 'react';

import { listValidationTasks } from '../services/validation';
import { getApiErrorMessage } from '../utils/apiError';

/**
 * Load the validation task queue, filtered by status server-side.
 *
 * Mirrors the loading/error/reload convention used by the other list hooks
 * (see `useApplications`), but talks to the queue endpoint directly since the
 * task list is only ever shown on the operator dashboard -- no shared store
 * is needed.
 */
export function useValidationTasks() {
  const [tasks, setTasks] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listValidationTasks({
        status: statusFilter || undefined,
        limit: 100,
      });
      setTasks(data.tasks);
      setTotal(data.total);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    // Fetch-on-mount via a memoized hook function -- see AuthProvider.jsx or
    // the full-stack audit (Phase 8) for why this react-hooks/set-state-in-effect
    // suppression is intentional, not a missed fix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
  }, [reload]);

  return {
    tasks,
    total,
    loading,
    error,
    reload,
    statusFilter,
    onStatusChange: setStatusFilter,
  };
}
