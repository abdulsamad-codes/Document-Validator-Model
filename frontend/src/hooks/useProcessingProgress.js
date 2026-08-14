import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  getProcessingDocuments,
  getProcessingProgress,
  retryProcessing,
  startProcessing,
} from '../services/processing';
import { getApiErrorMessage } from '../utils/apiError';
import { getPreference } from '../utils/preferences';

export function useProcessingProgress(applicationId) {
  const navigate = useNavigate();
  const [progress, setProgress] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);

  const navigateReportFiredRef = useRef(false);

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

  // One-shot navigation to the validation report when processing completes.
  useEffect(() => {
    const autoOpen = getPreference('openReportOnProcessingComplete', false);
    const completed =
      progress != null &&
      Number(progress.total_documents) > 0 &&
      Number(progress.completed) >= Number(progress.total_documents);
    if (!autoOpen || !completed) {
      navigateReportFiredRef.current = false;
      return;
    }
    if (navigateReportFiredRef.current) {
      return;
    }
    navigateReportFiredRef.current = true;
    navigate(`/reports?application=${applicationId}`);
  }, [progress, applicationId, navigate]);

  useEffect(() => {
    setLoading(true);
    reload();
    const autoRefresh = getPreference('autoRefreshProcessingStatus', true);
    if (!autoRefresh) {
      return undefined;
    }
    const interval = window.setInterval(reload, 2500);
    return () => window.clearInterval(interval);
  }, [reload]);

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
