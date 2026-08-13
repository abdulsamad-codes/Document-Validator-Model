import { Fragment } from 'react';

import { Pencil, X } from 'lucide-react';

import StatusChip from '../../common/StatusChip/StatusChip';
import { getRuleResultStatus } from '../../../data/statuses';
import styles from './ReviewFields.module.css';

function confidenceClass(score) {
  if (score == null) {
    return 'muted';
  }
  if (score >= 0.9) {
    return 'high';
  }
  if (score >= 0.7) {
    return 'medium';
  }
  return 'low';
}

/**
 * Extracted fields with their confidence and correction workflow.
 *
 * Each row shows the field, its source document, the extracted value, the
 * normalized value when available, the confidence score and the verification
 * status. Fields the reviewer has already confirmed or corrected are marked
 * reviewed and cannot be corrected again. All other fields can be flagged for
 * correction with a corrected value and an optional reason; corrections feed
 * the final CORRECT decision.
 *
 * @param {object} props
 * @param {object[]} props.fields The review screen's fields.
 * @param {object[]} props.corrections Current correction entries.
 * @param {Function} props.onCorrectionsChange Correction update handler.
 * @param {boolean} props.readOnly Disable correction actions.
 */
function ReviewFields({ fields, corrections, onCorrectionsChange, readOnly = false }) {
  if (!fields || fields.length === 0) {
    return (
      <p className={styles.empty}>No extracted fields are available for this application.</p>
    );
  }

  const correctionByField = new Map(corrections.map((correction) => [correction.field_name, correction]));

  const updateCorrection = (fieldName, patch) => {
    const current = correctionByField.get(fieldName);
    const next = { ...(current ?? {}), field_name: fieldName, ...patch };
    onCorrectionsChange([
      ...corrections.filter((correction) => correction.field_name !== fieldName),
      next,
    ]);
  };

  const addCorrection = (field) => {
    if (readOnly) {
      return;
    }
    const defaultValue = field.normalized_value || field.extracted_value || '';
    if (!correctionByField.has(field.field_name)) {
      onCorrectionsChange([
        ...corrections,
        { field_name: field.field_name, corrected_value: defaultValue, reason: '' },
      ]);
    }
  };

  const removeCorrection = (fieldName) => {
    onCorrectionsChange(corrections.filter((correction) => correction.field_name !== fieldName));
  };

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">Field</th>
          <th scope="col">Extracted value</th>
          <th scope="col">Normalized value</th>
          <th scope="col">Confidence</th>
          <th scope="col">Status</th>
          <th scope="col">
            <span className={styles.srOnly}>Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {fields.map((field) => {
          const status = getRuleResultStatus(field.verification_status);
          const reviewed = field.human_verified || field.human_corrected_value != null;
          const isCorrecting = correctionByField.has(field.field_name);
          const correction = correctionByField.get(field.field_name);
          return (
            <Fragment key={`${field.document_id}-${field.field_name}`}>
              <tr>
                <td data-label="Field" className={styles.fieldCell}>
                  <span className={styles.fieldName}>{field.field_name}</span>
                  <span className={styles.sourceDoc}>{field.file_name}</span>
                </td>
                <td data-label="Extracted value">{field.extracted_value || '—'}</td>
                <td data-label="Normalized value">
                  {field.normalized_value || '—'}
                  {field.human_corrected_value && (
                    <span className={styles.corrected}>
                      Corrected: {field.human_corrected_value}
                    </span>
                  )}
                </td>
                <td
                  data-label="Confidence"
                  className={`${styles.confidence} ${styles[confidenceClass(field.confidence_score)]}`}
                >
                  {field.confidence_score != null
                    ? `${Math.round(field.confidence_score * 100)}%`
                    : '—'}
                </td>
                <td data-label="Status">
                  {reviewed ? (
                    <StatusChip label="Reviewed" variant="success" />
                  ) : (
                    <StatusChip label={status.label} variant={status.variant} />
                  )}
                </td>
                <td data-label="Actions" className={styles.actionCell}>
                  {!readOnly && !reviewed && !isCorrecting && (
                    <button
                      type="button"
                      className={styles.correctBtn}
                      onClick={() => addCorrection(field)}
                    >
                      <Pencil aria-hidden="true" />
                      Correct
                    </button>
                  )}
                  {isCorrecting && (
                    <button
                      type="button"
                      className={styles.removeBtn}
                      onClick={() => removeCorrection(field.field_name)}
                      aria-label={`Cancel correction for ${field.field_name}`}
                    >
                      <X aria-hidden="true" />
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
              {isCorrecting && (
                <tr className={styles.correctionRow}>
                  <td colSpan="6" data-label="Correction">
                    <div className={styles.correctionInputs}>
                      <label className={styles.inputWrap}>
                        <span className={styles.inputLabel}>Corrected value</span>
                        <input
                          type="text"
                          className={styles.input}
                          value={correction.corrected_value ?? ''}
                          onChange={(event) =>
                            updateCorrection(field.field_name, {
                              corrected_value: event.target.value,
                            })
                          }
                        />
                      </label>
                      <label className={styles.inputWrap}>
                        <span className={styles.inputLabel}>Reason (optional)</span>
                        <input
                          type="text"
                          className={styles.input}
                          value={correction.reason ?? ''}
                          onChange={(event) =>
                            updateCorrection(field.field_name, { reason: event.target.value })
                          }
                        />
                      </label>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

export default ReviewFields;