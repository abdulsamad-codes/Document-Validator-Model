import { useEffect, useState } from 'react';

import { Info, RefreshCw } from 'lucide-react';

import ConfirmDialog from '../../components/common/ConfirmDialog/ConfirmDialog';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import { useToast } from '../../components/common/Toast/ToastContext';
import ReviewChecklist from '../../components/humanReview/ReviewChecklist/ReviewChecklist';
import ReviewDecision from '../../components/humanReview/ReviewDecision/ReviewDecision';
import ReviewDetections from '../../components/humanReview/ReviewDetections/ReviewDetections';
import ReviewDocuments from '../../components/humanReview/ReviewDocuments/ReviewDocuments';
import ReviewFields from '../../components/humanReview/ReviewFields/ReviewFields';
import ReviewHistory from '../../components/humanReview/ReviewHistory/ReviewHistory';
import ReviewSummary from '../../components/humanReview/ReviewSummary/ReviewSummary';
import { APPLICATION_STATUSES } from '../../data/statuses';
import { useAuth } from '../../hooks/useAuth';
import { useHumanReview } from '../../hooks/useHumanReview';
import { getPreference } from '../../utils/preferences';
import styles from './HumanReviewPage.module.css';

function Section({ title, children, note }) {
  return (
    <section className={styles.section} aria-label={title}>
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>{title}</h3>
      </div>
      {note && <p className={styles.sectionNote}>{note}</p>}
      {children}
    </section>
  );
}

function ReviewSkeleton() {
  return (
    <div aria-hidden="true">
      <div className={styles.skeletonHeader} />
      <div className={styles.skeletonTable} />
    </div>
  );
}

/**
 * Final human review workflow.
 *
 * Opens the stored review screen for a selected application and lets the
 * reviewer drive the final decision (approve / correct / reject) against the
 * full checklist, field corrections, documents, OCR state and signature/stamp
 * findings. An application can only be reviewed once: when a previous review
 * exists the page is read-only and shows the stored decision. Every action
 * refetches the backend state so the UI reflects the real response.
 */
function HumanReviewPage() {
  const { user } = useAuth();
  const {
    applications,
    appsLoading,
    appsError,
    statusFilter,
    onStatusChange,
    selectedId,
    onSelect,
    reviewScreen,
    history,
    loading,
    error,
    submitting,
    submitError,
    submit,
    alreadyReviewed,
    onRefresh,
  } = useHumanReview();
  const toast = useToast();

  const reviewerName = user?.name ?? '';

  const [decision, setDecision] = useState('');
  const [comments, setComments] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [checklist, setChecklist] = useState({});
  const [corrections, setCorrections] = useState([]);
  const [pendingRejectPayload, setPendingRejectPayload] = useState(null);

  useEffect(() => {
    setDecision('');
    setComments('');
    setRejectionReason('');
    setCorrections([]);
  }, [selectedId]);

  useEffect(() => {
    setChecklist(
      (reviewScreen?.checklist ?? []).reduce((acc, item) => {
        acc[item.item_name] = item.is_checked;
        return acc;
      }, {})
    );
  }, [reviewScreen?.checklist]);

  const checklistItems = reviewScreen?.checklist ?? [];
  const checklistPayload = checklistItems.map((item) => ({
    item_name: item.item_name,
    is_checked: Boolean(checklist[item.item_name]),
  }));

  const toggleChecklist = (itemName) => {
    setChecklist((prev) => ({ ...prev, [itemName]: !prev[itemName] }));
  };

  const handleSubmit = async (payload) => {
    if (payload.decision === 'REJECT' && getPreference('confirmBeforeRejectApplication', true)) {
      setPendingRejectPayload(payload);
      return;
    }
    await submitReview(payload);
  };

  const submitReview = async (payload) => {
    const result = await submit(payload);
    if (result) {
      toast.success('Final review submitted successfully.');
      setDecision('');
      setComments('');
      setRejectionReason('');
      setCorrections([]);
    }
  };

  const handleRejectConfirmed = () => {
    const payload = pendingRejectPayload;
    setPendingRejectPayload(null);
    if (payload) {
      void submitReview(payload);
    }
  };

  const readOnly = alreadyReviewed;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Human Review</h2>
        <p className={styles.subtitle}>
          Record the final decision for an application after reviewing its documents, extracted
          fields and verification findings.
        </p>
      </header>

      <div className={styles.toolbar}>
        <label className={styles.filter} htmlFor="review-app-select">
          <span className={styles.filterLabel}>Application</span>
          <select
            id="review-app-select"
            className={styles.select}
            value={selectedId ?? ''}
            onChange={(event) => onSelect(event.target.value)}
            aria-label="Select an application to review"
            disabled={appsLoading}
          >
            <option value="">Select an application</option>
            {applications.map((app) => (
              <option key={app.id} value={app.id}>
                #{app.id} — {app.name || app.created_by} ({app.status})
              </option>
            ))}
          </select>
        </label>

        <label className={styles.filter} htmlFor="review-status-filter">
          <span className={styles.filterLabel}>Status</span>
          <select
            id="review-status-filter"
            className={styles.select}
            value={statusFilter}
            onChange={(event) => onStatusChange(event.target.value)}
            aria-label="Filter applications by status"
          >
            <option value="">All</option>
            {APPLICATION_STATUSES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <button type="button" className={styles.secondaryBtn} onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>
      </div>

      {appsError && <ErrorState message={appsError} onRetry={onRefresh} />}

      {selectedId == null && !appsError && (
        <EmptyState
          title="Select an application"
          message="Choose an application above to open its final review."
        />
      )}

      {selectedId != null && loading && <ReviewSkeleton />}

      {selectedId != null && !loading && error && (
        <ErrorState message={error} onRetry={onRefresh} />
      )}

      {selectedId != null && !loading && !error && reviewScreen && (
        <>
          <ReviewSummary reviewScreen={reviewScreen} />

          {readOnly && (
            <div className={styles.readOnlyBanner} role="status">
              <Info className={styles.bannerIcon} aria-hidden="true" />
              <div>
                <strong>This application has already been finally reviewed.</strong>
                <p>
                  The decision below is the stored record. No further review can be submitted for
                  this application.
                </p>
              </div>
            </div>
          )}

          <Section title="Documents" note="Uploaded documents and their processing state">
            <ReviewDocuments documents={reviewScreen.documents} />
          </Section>

          <Section
            title="Extracted Fields"
            note={
              readOnly
                ? 'Stored extracted, normalized and confidence-scored fields.'
                : 'Correct a field to include a correction in a CORRECT decision.'
            }
          >
            <ReviewFields
              fields={reviewScreen.fields}
              corrections={corrections}
              onCorrectionsChange={setCorrections}
              readOnly={readOnly}
            />
          </Section>

          <Section title="Signature & Stamp Findings">
            <ReviewDetections detections={reviewScreen.visual_detections} />
          </Section>

          <Section
            title="Manual Checklist"
            note="Confirm every item by hand. All items are required to approve."
          >
            <ReviewChecklist
              items={checklistItems}
              checked={checklist}
              onToggle={toggleChecklist}
              readOnly={readOnly}
            />
          </Section>

          {!readOnly ? (
            <Section title="Decision">
              <ReviewDecision
                reviewerName={reviewerName}
                decision={decision}
                onDecisionChange={setDecision}
                comments={comments}
                onCommentsChange={setComments}
                rejectionReason={rejectionReason}
                onRejectionReasonChange={setRejectionReason}
                checklist={checklistPayload}
                corrections={corrections}
                submitting={submitting}
                readOnly={false}
                submitError={submitError}
                onSubmit={handleSubmit}
              />
            </Section>
          ) : (
            <Section title="Review History" note="Stored final review record for this application.">
              <ReviewHistory reviews={history} />
            </Section>
          )}
        </>
      )}

      <ConfirmDialog
        open={pendingRejectPayload != null}
        title="Reject this application?"
        message={`Application #${selectedId} will be rejected. The rejection reason will be recorded permanently and the application cannot be approved afterwards.`}
        confirmLabel="Reject application"
        tone="danger"
        onConfirm={handleRejectConfirmed}
        onCancel={() => setPendingRejectPayload(null)}
      />
    </div>
  );
}

export default HumanReviewPage;