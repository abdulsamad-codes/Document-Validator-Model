import StatusChip from '../../common/StatusChip/StatusChip';
import { getDocumentStatus, getRuleResultStatus } from '../../../data/statuses';
import { getDocumentTypeConfig } from '../../../data/documents';
import styles from './ReportDocuments.module.css';

/**
 * Per-document status table from the validation report.
 *
 * Each row shows the document type, processing outcome, OCR outcome and the
 * technical-validation and analysis results, plus OCR confidence when the
 * pipeline produced it.
 *
 * @param {object} props
 * @param {object[]} props.documents The report's `document_summary` rows.
 */
function ReportDocuments({ documents }) {
  if (!documents || documents.length === 0) {
    return (
      <p className={styles.empty}>No documents were included in this report.</p>
    );
  }

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">Document</th>
          <th scope="col">Processing</th>
          <th scope="col">OCR</th>
          <th scope="col">Technical</th>
          <th scope="col">Analysis</th>
          <th scope="col">Confidence</th>
        </tr>
      </thead>
      <tbody>
        {documents.map((document) => {
          const config = getDocumentTypeConfig(document.document_type);
          const processing = getDocumentStatus(document.processing_status);
          const ocr = getRuleResultStatus(document.ocr_status);
          const technical = getRuleResultStatus(document.technical_validation_status);
          const analysis = getRuleResultStatus(document.analysis_status);
          return (
            <tr key={document.document_id}>
              <td data-label="Document" className={styles.typeCell}>
                {config.label}
              </td>
              <td data-label="Processing">
                <StatusChip label={processing.label} variant={processing.variant} />
              </td>
              <td data-label="OCR">
                <StatusChip label={ocr.label} variant={ocr.variant} />
              </td>
              <td data-label="Technical">
                <StatusChip label={technical.label} variant={technical.variant} />
              </td>
              <td data-label="Analysis">
                <StatusChip label={analysis.label} variant={analysis.variant} />
              </td>
              <td data-label="Confidence" className={styles.confidenceCell}>
                {document.ocr_confidence != null
                  ? `${Math.round(document.ocr_confidence * 100)}%`
                  : '—'}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default ReportDocuments;