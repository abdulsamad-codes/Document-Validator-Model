import { useCallback, useEffect, useState } from 'react';

import {
  getValidationTask,
  getValidationTaskLogs,
  getValidationTaskResults,
} from '../services/validation';
import { getApiErrorMessage } from '../utils/apiError';

/**
 * Load one validation task with its stored check results and audit log.
 *
 * Used by the operator dashboard's review panel once a queue row is
 * selected. `taskId` of `null` skips fetching (no row selected yet).
 *
 * @param {number|string|null} taskId Task id, or `null` when nothing is selected.
 */
export function useValidationTask(taskId) {
  const [task, setTask] = useState(null);
  const [results, setResults] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    if (!taskId) {
      setTask(null);
      setResults([]);
      setLogs([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [taskData, resultsData, logsData] = await Promise.all([
        getValidationTask(taskId),
        getValidationTaskResults(taskId, { limit: 100 }),
        getValidationTaskLogs(taskId, { limit: 50 }),
      ]);
      setTask(taskData);
      setResults(resultsData.results);
      setLogs(logsData.logs);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    // Fetch-on-mount via a memoized hook function -- see AuthProvider.jsx or
    // the full-stack audit (Phase 8) for why this react-hooks/set-state-in-effect
    // suppression is intentional, not a missed fix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
  }, [reload]);

  return { task, results, logs, loading, error, reload };
}
