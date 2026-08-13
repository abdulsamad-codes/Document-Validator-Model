import { useCallback, useEffect, useState } from 'react';

import { getApplication, listApplications } from '../services/applications';
import { getReviewHistory, getReviewScreen, submitHumanReview } from '../services/humanReview';
import { getApiErrorMessage } from '../utils/apiError';

const DEFAULT_STATUS = 'PENDING_REVIEW';

const FINALIZED_STATUSES = ['APPROVED', 'REJECTED', 'CORRECTED'];

/**
 * Load everything the final Human Review page needs.
 *
 * Applications are listed through the shared list endpoint (optionally
 * filtered by status, defaulting to applications awaiting review). Selecting
 * an application opens its review screen, application record and review
 * history in parallel. Submitting a decision always refetches the backend
 * state so the UI reflects the stored result, not local state.
 */
export function useHumanReview() {
  const [applications, setApplications] = useState([]);
  const [appsLoading, setAppsLoading] = useState(true);
  const [appsError, setAppsError] = useState(null);
  const [statusFilter, setStatusFilter] = useState(DEFAULT_STATUS);
  const [selectedId, setSelectedId] = useState(null);

  const [reviewScreen, setReviewScreen] = useState(null);
  const [application, setApplication] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const loadApplications = useCallback(async () => {
    setAppsLoading(true);
    setAppsError(null);
    try {
      const { items } = await listApplications({
        status: statusFilter || undefined,
        limit: 100,
      });
      setApplications(items ?? []);
    } catch (err) {
      setAppsError(getApiErrorMessage(err));
      setApplications([]);
    } finally {
      setAppsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadApplications();
  }, [loadApplications]);

  const reload = useCallback(async () => {
    if (selectedId == null) {
      setReviewScreen(null);
      setApplication(null);
      setHistory([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [screen, app, reviews] = await Promise.all([
        getReviewScreen(selectedId),
        getApplication(selectedId),
        getReviewHistory(selectedId),
      ]);
      setReviewScreen(screen);
      setApplication(app);
      setHistory(reviews?.reviews ?? []);
    } catch (err) {
      setError(getApiErrorMessage(err));
      setReviewScreen(null);
      setApplication(null);
      setHistory([]);
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleStatusChange = useCallback((value) => {
    setStatusFilter(value);
    setSelectedId(null);
  }, []);

  const handleSelect = useCallback((value) => {
    setSelectedId(value === '' ? null : Number(value));
  }, []);

  const alreadyReviewed =
    reviewScreen?.previous_review != null ||
    (application != null && FINALIZED_STATUSES.includes(application.status));

  const submit = useCallback(
    async (payload) => {
      if (selectedId == null) {
        return null;
      }
      setSubmitting(true);
      setSubmitError(null);
      try {
        const result = await submitHumanReview(selectedId, payload);
        await reload();
        return result;
      } catch (err) {
        const message = getApiErrorMessage(err);
        setSubmitError(message);
        return null;
      } finally {
        setSubmitting(false);
      }
    },
    [selectedId, reload]
  );

  const handleRefresh = useCallback(() => {
    loadApplications();
    reload();
  }, [loadApplications, reload]);

  return {
    applications,
    appsLoading,
    appsError,
    statusFilter,
    onStatusChange: handleStatusChange,
    selectedId,
    onSelect: handleSelect,
    reviewScreen,
    application,
    history,
    loading,
    error,
    submitting,
    submitError,
    submit,
    alreadyReviewed,
    onRefresh: handleRefresh,
  };
}