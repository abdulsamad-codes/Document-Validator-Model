import { useCallback, useEffect, useState } from 'react';

import {
  getProcessingDocuments,
  getProcessingProgress,
  retryProcessing,
  startProcessing,
} from '../services/processing';
import { getApiErrorMessage } from '../utils/apiError';

export function useProcessingProgress(applicationId) {
  const [progress, setProgress] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    try {
      const [nextProgress, nextDocuments] = await Promise.all([
        getProcessingProgress(applicationId),
        getProcessingDocuments(applicationId),
      ]);
      setProgress(nextProgress);
      setDocuments(nextDocuments.documents ?? []);
      setError(null);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    setLoading(true);
    reload();
    const interval = window.setInterval(reload, 2500);
    return () => window.clearInterval(interval);
  }, [reload]);

  const runAction = useCallback(async (action) => {
    setActionLoading(true);
    try {
      const result = await action(applicationId);
      await reload();
      return result;
    } finally {
      setActionLoading(false);
    }
  }, [applicationId, reload]);

  return {
    progress,
    documents,
    loading,
    actionLoading,
    error,
    reload,
    start: () => runAction(startProcessing),
    retry: () => runAction(retryProcessing),
  };
}
