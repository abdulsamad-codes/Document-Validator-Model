import { AlertTriangle, Check, Send } from 'lucide-react';

import styles from './ReviewDecision.module.css';

const DECISIONS = [
  {
    value: 'APPROVE',
    label: 'Approve',
    description: 'Approves the application. Every checklist item must be checked.',
  },
  {
    value: 'CORRECT',
    label: 'Correct',
    description: 'Records corrected field values and marks the application as corrected.',
  },
  {
    value: 'REJECT',
    label: 'Reject',
    description: 'Rejects the application. A rejection reason is required.',
  },
];

/**
 * Final decision form.
 *
 * Lets the reviewer choose the decision (approve / correct / reject), add
 * comments, provide the mandatory rejection reason and submit. Client-side
 * validation mirrors the backend rules (full checklist to approve, at least
 * one correction to correct, reason to reject).
 *
 * @param {object} props
 * @param {string} props.reviewerName Current reviewer name.
 * @param {string} props.decision Selected decision value.
 * @param {Function} props.onDecisionChange Decision handler.
 * @param {string} props.comments Review comments.
 * @param {Function} props.onCommentsChange Comments handler.
 * @param {string} props.rejectionReason Rejection reason.
 * @param {Function} props.onRejectionReasonChange Rejection reason handler.
 * @param {object[]} props.checklist Checklist items with state.
 * @param {object[]} props.corrections Field corrections.
 * @param {boolean} props.submitting Submission in progress.
 * @param {boolean} props.readOnly Disable the form.
 * @param {string|null} props.submitError Server-side error message.
 * @param {Function} props.onSubmit Payload submit handler.
 */
function ReviewDecision({
  reviewerName,
  decision,
  onDecisionChange,
  comments,
  onCommentsChange,
  rejectionReason,
  onRejectionReasonChange,
  checklist,
  corrections,
  submitting,
  readOnly,
  submitError,
  onSubmit,
}) {
  // checklist.every() is vacuously true on an empty array, so require at
  // least one item before treating the checklist as complete -- otherwise
  // an application with no checklist items could be approved unchecked.
  const checklistComplete = checklist.length > 0 && checklist.every((item) => item.is_checked);
  const hasCorrection = corrections.some((correction) => (correction.corrected_value ?? '').trim());

  let validationError = null;
  if (!reviewerName) {
    validationError = 'Your reviewer name could not be determined. Contact your administrator.';
  } else if (!decision) {
    validationError = 'Choose a decision to continue.';
  } else if (decision === 'APPROVE' && !checklistComplete) {
    validationError = 'Every checklist item must be checked to approve.';
  } else if (decision === 'CORRECT' && !hasCorrection) {
    validationError = 'Add at least one field correction to correct.';
  } else if (decision === 'REJECT' && !rejectionReason.trim()) {
    validationError = 'A rejection reason is required to reject.';
  }

  const handleSubmit = () => {
    if (validationError || submitting || readOnly) {
      return;
    }
    onSubmit({
      reviewer_name: reviewerName,
      decision,
      comments: comments.trim() ? comments : null,
      rejection_reason: decision === 'REJECT' ? rejectionReason.trim() : null,
      checklist: checklist.map((item) => ({
        item_name: item.item_name,
        is_checked: item.is_checked,
      })),
      corrections: corrections
        .filter((correction) => (correction.corrected_value ?? '').trim())
        .map((correction) => ({
          field_name: correction.field_name,
          document_id: correction.document_id ?? null,
          corrected_value: correction.corrected_value.trim(),
          reason: (correction.reason ?? '').trim() || null,
        })),
    });
  };

  return (
    <div className={styles.panel}>
      <div className={styles.decisions}>
        {DECISIONS.map((option) => (
          <label
            key={option.value}
            className={`${styles.option} ${decision === option.value ? styles.optionActive : ''}`}
          >
            <input
              type="radio"
              name="review-decision"
              value={option.value}
              className={styles.radio}
              checked={decision === option.value}
              disabled={readOnly}
              onChange={() => onDecisionChange(option.value)}
            />
            <span className={styles.optionLabel}>{option.label}</span>
            <span className={styles.optionDescription}>{option.description}</span>
          </label>
        ))}
      </div>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>Comments (optional)</span>
        <textarea
          className={styles.textarea}
          rows="3"
          value={comments}
          disabled={readOnly}
          onChange={(event) => onCommentsChange(event.target.value)}
          placeholder="Notes for the review record"
        />
      </label>

      {decision === 'REJECT' && (
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Rejection reason (required)</span>
          <textarea
            className={`${styles.textarea} ${styles.reason}`}
            rows="2"
            value={rejectionReason}
            disabled={readOnly}
            onChange={(event) => onRejectionReasonChange(event.target.value)}
            placeholder="Explain why the application is rejected"
          />
        </label>
      )}

      {validationError && (
        <div className={styles.validationError} role="alert">
          <AlertTriangle className={styles.errorIcon} aria-hidden="true" />
          {validationError}
        </div>
      )}

      {submitError && (
        <div className={styles.submitError} role="alert">
          <AlertTriangle className={styles.errorIcon} aria-hidden="true" />
          {submitError}
        </div>
      )}

      {!readOnly && (
        <button
          type="button"
          className={styles.submitBtn}
          disabled={Boolean(validationError) || submitting}
          onClick={handleSubmit}
        >
          {submitting ? (
            <>
              <Send className={styles.submitIcon} aria-hidden="true" />
              Submitting…
            </>
          ) : (
            <>
              <Check className={styles.submitIcon} aria-hidden="true" />
              Submit decision
            </>
          )}
        </button>
      )}
    </div>
  );
}

export default ReviewDecision;