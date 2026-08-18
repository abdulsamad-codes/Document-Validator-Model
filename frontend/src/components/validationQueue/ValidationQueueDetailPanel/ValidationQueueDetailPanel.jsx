import { useState } from 'react';

import { FileText, History, Send, ShieldAlert } from 'lucide-react';

import ConfirmDialog from '../../common/ConfirmDialog/ConfirmDialog';
import StatusChip from '../../common/StatusChip/StatusChip';
import { getApplicationStatus, getValidationHistoryEvent } from '../../../data/statuses';
import { getDocumentTypeConfig } from '../../../data/documents';
import { formatDateTime } from '../../../utils/format';
import styles from './ValidationQueueDetailPanel.module.css';

const ALL_REQUIRED_DOCUMENT_TYPES = [
  'TRIPARTITE_AGREEMENT',
  'BILATERAL_AGREEMENT',
  'ACCOUNT_MAINTENANCE_CERTIFICATE',
  'ONE_LINK_LETTER',
  'AUTHORITY_LETTER',
  'SCHEDULE_OF_CHARGES',
  'BUSINESS_REQUIREMENT_DOCUMENT',
  'FORMAL_REQUEST_LETTER',
];

/**
 * Action + history panel for a selected application in the validation queue.
 *
 * The operator can request missing documents (pre-checked from the
 * application's own missing list, editable), reject the application with a
 * mandatory reason, or submit a complete application for processing. All three
 * actions are only shown to operators; other roles see a read-only note. The
 * immutable validation history is shown below.
 *
 * @param {object} props
 * @param {object} props.application Selected validation queue item.
 * @param {Array<object>} props.history Validation history entries.
 * @param {boolean} props.historyLoading Whether history is loading.
 * @param {string|null} props.historyError History fetch error message.
 * @param {boolean} props.canOperate Whether the current user may run actions.
 * @param {boolean} props.actionLoading Whether an action is in flight.
 * @param {string|null} props.actionError Last action error message.
 * @param {Function} props.onRequestDocuments Callback(payload) for requesting
 *   documents: `{ missingDocumentTypes, reason }`.
 * @param {Function} props.onReject Callback(payload) for rejection: `{ reason }`.
 * @param {Function} props.onSubmit Callback() for submitting for processing.
 */
function ValidationQueueDetailPanel({
  application,
  history,
  historyLoading,
  historyError,
  canOperate,
  actionLoading,
  actionError,
  onRequestDocuments,
  onReject,
  onSubmit,
}) {
  const [selectedDocuments, setSelectedDocuments] = useState(
    () => new Set(application.missing_documents ?? [])
  );
  const [requestReason, setRequestReason] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [pendingReject, setPendingReject] = useState(false);

  const status = getApplicationStatus(application.status);

  const toggleDocument = (type) => {
    setSelectedDocuments((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  const handleRequestDocuments = () => {
    const missingDocumentTypes = [...selectedDocuments];
    if (missingDocumentTypes.length === 0) {
      return;
    }
    onRequestDocuments({ missingDocumentTypes, reason: requestReason.trim() || undefined });
  };

  const handleReject = () => {
    if (!rejectReason.trim()) {
      return;
    }
    setPendingReject(true);
  };

  const handleRejectConfirmed = () => {
    setPendingReject(false);
    onReject({ reason: rejectReason.trim() });
  };

  const handleSubmit = () => {
    onSubmit();
  };

  return (
    <section className={styles.panel} aria-label={`Validation actions for application ${application.application_id}`}>
      <div className={styles.header}>
        <h3 className={styles.title}>
          {application.application_name || `Application #${application.application_id}`}
        </h3>
        <div className={styles.statusRow}>
          <StatusChip label={status.label} variant={status.variant} />
          <span className={styles.completion}>
            {application.received_document_count} of {application.required_document_count} documents ·
            {Math.round(application.completion_percentage)}% complete
          </span>
        </div>
      </div>

      {!canOperate && (
        <p className={styles.readOnlyNote} role="note">
          You have view-only access to this queue. Only operators can request documents, reject or
          submit applications.
        </p>
      )}

      {canOperate && (
        <div className={styles.actions}>
          <div className={styles.actionSection}>
            <div className={styles.sectionHeader}>
              <FileText className={styles.sectionIcon} aria-hidden="true" />
              <span className={styles.sectionTitle}>Request missing documents</span>
            </div>
            <p className={styles.sectionHint}>
              Select the documents the applicant must still provide, then send the request.
            </p>
            <ul className={styles.documentList}>
              {ALL_REQUIRED_DOCUMENT_TYPES.map((type) => {
                const config = getDocumentTypeConfig(type);
                const checked = selectedDocuments.has(type);
                return (
                  <li key={type}>
                    <label className={styles.documentOption}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleDocument(type)}
                      />
                      <span className={styles.documentLabel}>{config.label}</span>
                      {checked && <StatusChip label="Requested" variant="warning" />}
                    </label>
                  </li>
                );
              })}
            </ul>
            <label className={styles.reasonField} htmlFor="request-documents-reason">
              <span className={styles.reasonLabel}>Note for the applicant (optional)</span>
              <textarea
                id="request-documents-reason"
                className={styles.reasonInput}
                value={requestReason}
                onChange={(event) => setRequestReason(event.target.value)}
                maxLength={2000}
                rows={3}
                placeholder="Explain which documents are still required and why."
              />
            </label>
            <div className={styles.actionRow}>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={actionLoading || selectedDocuments.size === 0}
                onClick={handleRequestDocuments}
              >
                <Send aria-hidden="true" />
                Request documents
              </button>
            </div>
          </div>

          <div className={styles.actionSection}>
            <div className={styles.sectionHeader}>
              <ShieldAlert className={styles.sectionIcon} aria-hidden="true" />
              <span className={styles.sectionTitle}>Decision</span>
            </div>
            <p className={styles.sectionHint}>
              Submit the application for processing when its documents are complete, or reject it
              with a reason.
            </p>
            <label className={styles.reasonField} htmlFor="reject-reason">
              <span className={styles.reasonLabel}>Rejection reason (required to reject)</span>
              <textarea
                id="reject-reason"
                className={styles.reasonInput}
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                maxLength={2000}
                rows={3}
                placeholder="State why this application cannot proceed."
              />
            </label>
            <div className={styles.actionRow}>
              <button
                type="button"
                className={styles.submitButton}
                disabled={actionLoading}
                onClick={handleSubmit}
              >
                Submit for processing
              </button>
              <button
                type="button"
                className={styles.dangerButton}
                disabled={actionLoading || !rejectReason.trim()}
                onClick={handleReject}
              >
                Reject application
              </button>
            </div>
          </div>

          {actionError && (
            <p className={styles.errorText} role="alert">
              {actionError}
            </p>
          )}
        </div>
      )}

      <div className={styles.history}>
        <div className={styles.sectionHeader}>
          <History className={styles.sectionIcon} aria-hidden="true" />
          <span className={styles.sectionTitle}>Application history</span>
        </div>
        {historyLoading ? (
          <p className={styles.mutedText}>Loading history…</p>
        ) : historyError ? (
          <p className={styles.errorText} role="alert">
            {historyError}
          </p>
        ) : history.length === 0 ? (
          <p className={styles.mutedText}>No activity recorded yet.</p>
        ) : (
          <ol className={styles.timeline}>
            {history.map((entry) => {
              const event = getValidationHistoryEvent(entry.event_type);
              return (
                <li key={entry.id} className={styles.timelineItem}>
                  <div className={styles.timelineDot} aria-hidden="true" />
                  <div className={styles.timelineBody}>
                    <div className={styles.timelineHeader}>
                      <StatusChip label={event.label} variant={event.variant} />
                      <span className={styles.timelineTime}>{formatDateTime(entry.created_at)}</span>
                    </div>
                    {(entry.actor_name || entry.actor_role) && (
                      <p className={styles.timelineActor}>
                        {[entry.actor_name, entry.actor_role].filter(Boolean).join(' · ')}
                      </p>
                    )}
                    {entry.reason && <p className={styles.timelineReason}>{entry.reason}</p>}
                    {entry.missing_document_types?.length > 0 && (
                      <p className={styles.timelineDetail}>
                        Requested:{' '}
                        {entry.missing_document_types
                          .map((type) => getDocumentTypeConfig(type).label)
                          .join(', ')}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <ConfirmDialog
        open={pendingReject}
        title="Reject this application?"
        message={`Application #${application.application_id} will be rejected. The reason is recorded permanently and the application cannot be submitted afterwards.`}
        confirmLabel="Reject application"
        tone="danger"
        loading={actionLoading}
        onConfirm={handleRejectConfirmed}
        onCancel={() => setPendingReject(false)}
      />
    </section>
  );
}

export default ValidationQueueDetailPanel;