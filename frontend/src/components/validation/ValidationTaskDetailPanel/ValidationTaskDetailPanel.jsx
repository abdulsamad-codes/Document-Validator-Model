import { useState } from 'react';

import { CheckCircle2, ClipboardList, History, Play, X, XCircle } from 'lucide-react';

import { getValidationTaskStatus, getVerificationStatus } from '../../../data/statuses';
import { useValidationTask } from '../../../hooks/useValidationTask';
import {
  completeValidationTask,
  rejectValidationTask,
  requestValidationCorrection,
  startValidationTask,
} from '../../../services/validation';
import { getApiErrorMessage } from '../../../utils/apiError';
import { formatDateTime, humanizeEnum } from '../../../utils/format';
import ConfirmDialog from '../../common/ConfirmDialog/ConfirmDialog';
import ErrorState from '../../common/ErrorState/ErrorState';
import Spinner from '../../common/Spinner/Spinner';
import StatusChip from '../../common/StatusChip/StatusChip';
import styles from './ValidationTaskDetailPanel.module.css';

function ResultRow({ result }) {
  const status = getVerificationStatus(result.status);
  return (
    <li className={styles.item}>
      <div className={styles.itemHeader}>
        <span className={styles.itemName}>{result.rule_name}</span>
        <StatusChip label={status.label} variant={status.variant} />
      </div>
      <p className={styles.itemMeta}>{humanizeEnum(result.rule_category)}</p>
      {result.message && <p className={styles.itemMessage}>{result.message}</p>}
    </li>
  );
}

function LogRow({ log }) {
  return (
    <li className={styles.item}>
      <div className={styles.itemHeader}>
        <span className={styles.itemName}>{humanizeEnum(log.action)}</span>
        <span className={styles.itemTime}>{formatDateTime(log.created_at)}</span>
      </div>
      {(log.field_name || log.result) && (
        <p className={styles.itemMeta}>
          {[log.field_name, log.result].filter(Boolean).join(' — ')}
        </p>
      )}
      {log.reason && <p className={styles.itemMessage}>{log.reason}</p>}
    </li>
  );
}

/**
 * Operator review panel for one validation task.
 *
 * Shows the task's stored check results and audit log, and drives the task
 * lifecycle (start / complete / reject / request-correction) through the
 * validation API. Reject and request-correction require a reason, entered
 * inline since neither action is a simple yes/no confirmation.
 *
 * @param {object} props
 * @param {number} props.taskId Task under review.
 * @param {Function} props.onClose Close handler.
 * @param {Function} props.onQueueChange Called after a lifecycle action
 *   succeeds, so the caller can refresh the queue list.
 */
function ValidationTaskDetailPanel({ taskId, onClose, onQueueChange }) {
  const { task, results, logs, loading, error, reload } = useValidationTask(taskId);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [reasonMode, setReasonMode] = useState(null); // 'reject' | 'correction' | null
  const [reasonText, setReasonText] = useState('');
  const [confirmingComplete, setConfirmingComplete] = useState(false);

  const runAction = async (action) => {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      await reload();
      onQueueChange();
      setReasonMode(null);
      setReasonText('');
      setConfirmingComplete(false);
    } catch (err) {
      setActionError(getApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStart = () => runAction(() => startValidationTask(taskId));
  const handleComplete = () => runAction(() => completeValidationTask(taskId));
  const handleSubmitReason = () => {
    if (!reasonText.trim()) {
      return;
    }
    runAction(() =>
      reasonMode === 'reject'
        ? rejectValidationTask(taskId, reasonText.trim())
        : requestValidationCorrection(taskId, reasonText.trim())
    );
  };

  const status = task ? getValidationTaskStatus(task.status) : null;

  return (
    <section className={styles.panel} aria-label="Validation task review">
      <div className={styles.header}>
        <div className={styles.heading}>
          <div className={styles.iconWrap} aria-hidden="true">
            <ClipboardList />
          </div>
          <div>
            <h3 className={styles.title}>Task #{taskId}</h3>
            {task && <p className={styles.subtitle}>Application #{task.application_id}</p>}
          </div>
        </div>
        <div className={styles.headerActions}>
          {status && <StatusChip label={status.label} variant={status.variant} />}
          <button type="button" className={styles.close} onClick={onClose} aria-label="Close review panel">
            <X aria-hidden="true" />
          </button>
        </div>
      </div>

      {loading && !task ? (
        <div className={styles.loading}>
          <Spinner size="medium" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : (
        <>
          {actionError && <p className={styles.actionError}>{actionError}</p>}

          <div className={styles.actionBar}>
            {task?.status === 'PENDING' && (
              <button type="button" className={styles.primaryBtn} disabled={busy} onClick={handleStart}>
                <Play aria-hidden="true" />
                Start Review
              </button>
            )}
            {task?.status === 'IN_REVIEW' && (
              <>
                <button
                  type="button"
                  className={styles.primaryBtn}
                  disabled={busy}
                  onClick={() => setConfirmingComplete(true)}
                >
                  <CheckCircle2 aria-hidden="true" />
                  Complete
                </button>
                <button
                  type="button"
                  className={styles.dangerBtn}
                  disabled={busy}
                  onClick={() => setReasonMode(reasonMode === 'reject' ? null : 'reject')}
                >
                  <XCircle aria-hidden="true" />
                  Reject
                </button>
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  disabled={busy}
                  onClick={() => setReasonMode(reasonMode === 'correction' ? null : 'correction')}
                >
                  Request Correction
                </button>
              </>
            )}
          </div>

          {reasonMode && (
            <div className={styles.reasonForm}>
              <label className={styles.reasonLabel} htmlFor="task-reason">
                {reasonMode === 'reject' ? 'Rejection reason' : 'Correction reason'} (required)
              </label>
              <textarea
                id="task-reason"
                className={styles.reasonInput}
                value={reasonText}
                onChange={(event) => setReasonText(event.target.value)}
                rows={3}
              />
              <div className={styles.reasonActions}>
                <button
                  type="button"
                  className={styles.cancelBtn}
                  onClick={() => {
                    setReasonMode(null);
                    setReasonText('');
                  }}
                  disabled={busy}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={reasonMode === 'reject' ? styles.dangerBtn : styles.secondaryBtn}
                  onClick={handleSubmitReason}
                  disabled={busy || !reasonText.trim()}
                >
                  Submit
                </button>
              </div>
            </div>
          )}

          <div className={styles.section}>
            <h4 className={styles.sectionTitle}>Check Results ({results.length})</h4>
            {results.length === 0 ? (
              <p className={styles.empty}>No stored check results for this application yet.</p>
            ) : (
              <ul className={styles.list}>
                {results.map((result) => (
                  <ResultRow key={result.id} result={result} />
                ))}
              </ul>
            )}
          </div>

          <div className={styles.section}>
            <h4 className={styles.sectionTitle}>
              <History aria-hidden="true" className={styles.sectionIcon} />
              Audit Log ({logs.length})
            </h4>
            {logs.length === 0 ? (
              <p className={styles.empty}>No log entries yet.</p>
            ) : (
              <ul className={styles.list}>
                {logs.map((log) => (
                  <LogRow key={log.id} log={log} />
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      <ConfirmDialog
        open={confirmingComplete}
        title="Complete validation"
        message="This marks the task as VALIDATED and closes the review. This cannot be undone."
        confirmLabel="Complete"
        tone="primary"
        loading={busy}
        onConfirm={handleComplete}
        onCancel={() => setConfirmingComplete(false)}
      />
    </section>
  );
}

export default ValidationTaskDetailPanel;
