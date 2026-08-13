import StatusChip from '../../common/StatusChip/StatusChip';
import { getRuleResultStatus } from '../../../data/statuses';
import styles from './ReportFields.module.css';

/**
 * Extracted and normalized field results.
 *
 * Prefers the stored normalized fields (each row carries the extracted value,
 * the canonical normalized value and the verification status); when
 * normalization has not run, falls back to the extracted fields captured by
 * document analysis.
 *
 * @param {object} props
 * @param {object[]} props.normalized Stored normalized field records.
 * @param {object[]} props.analysisItems Document-analysis result rows.
 */
function ReportFields({ normalized, analysisItems }) {
  if (normalized && normalized.length > 0) {
    return (
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Field</th>
            <th scope="col">Source document</th>
            <th scope="col">Extracted value</th>
            <th scope="col">Normalized value</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {normalized.map((field, index) => {
            const status = getRuleResultStatus(field.verification_status);
            return (
              <tr key={`${field.document_id}-${field.field_name}-${index}`}>
                <td data-label="Field" className={styles.fieldCell}>
                  {field.field_name}
                </td>
                <td data-label="Source document" className={styles.mutedCell}>
                  {field.file_name}
                </td>
                <td data-label="Extracted value">{field.extracted_value || '—'}</td>
                <td data-label="Normalized value">{field.normalized_value || '—'}</td>
                <td data-label="Status">
                  <StatusChip label={status.label} variant={status.variant} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  const withFields = (analysisItems ?? []).filter(
    (item) => item.extracted_fields && Object.keys(item.extracted_fields).length > 0
  );

  if (withFields.length > 0) {
    return (
      <div className={styles.docList}>
        {withFields.map((item) => (
          <div key={item.document_id} className={styles.docCard}>
            <h4 className={styles.docTitle}>{item.file_name}</h4>
            <dl className={styles.fieldList}>
              {Object.entries(item.extracted_fields).map(([name, value]) => (
                <div key={name} className={styles.fieldRow}>
                  <dt className={styles.fieldName}>{name}</dt>
                  <dd className={styles.fieldValue}>{value ?? '—'}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    );
  }

  return (
    <p className={styles.empty}>
      No extracted field results are available for this application.
    </p>
  );
}

export default ReportFields;