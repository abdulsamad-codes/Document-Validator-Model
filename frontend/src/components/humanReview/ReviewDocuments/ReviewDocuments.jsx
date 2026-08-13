import StatusChip from '../../common/StatusChip/StatusChip';
import { getDocumentStatus, getRuleResultStatus } from '../../../data/statuses';
import { getDocumentTypeConfig } from '../../../data/documents';
import { formatDateTime } from '../../../utils/format';
import styles from './ReviewDocuments.module.css';

/**
 * Uploaded documents with their processing and OCR state.
 *
 * Each row shows the document type, processing outcome, OCR outcome,
 * confidence and upload time. The raw OCR text preview is hidden behind a
 * disclosure so reviewers can inspect it without overwhelming the screen.
 *
 * @param {object} props
 * @param {object[]} props.documents The review screen's documents.
 */
function ReviewDocuments({ documents }) {
  if (!documents || documents.length === 0) {
    return (
      <p className={styles.empty}>No documents were uploaded for this application.</p>
    );
  }

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">Document</th>
          <th scope="col">Processing</th>
          <th scope="col">OCR</th>
          <th scope="col">Confidence</th>
          <th scope="col">Uploaded</th>
        </tr>
      </thead>
      <tbody>
        {documents.map((document) => {
          const config = getDocumentTypeConfig(document.document_type);
          const processing = getDocumentStatus(document.processing_status);
          const ocr = getRuleResultStatus(document.ocr_status);
          return (
            <tr key={document.document_id}>
              <td data-label="Document" className={styles.fileCell}>
                <span className={styles.typeLabel}>{config.label}</span>
                <span className={styles.fileName}>{document.original_filename}</span>
                {document.ocr_text_preview && (
                  <details className={styles.preview}>
                    <summary>View OCR text preview</summary>
                    <p className={styles.previewText}>{document.ocr_text_preview}</p>
                  </details>
                )}
              </td>
              <td data-label="Processing">
                <StatusChip label={processing.label} variant={processing.variant} />
              </td>
              <td data-label="OCR">
                <StatusChip label={ocr.label} variant={ocr.variant} />
              </td>
              <td data-label="Confidence" className={styles.mutedCell}>
                {document.ocr_confidence != null
                  ? `${Math.round(document.ocr_confidence * 100)}%`
                  : '—'}
              </td>
              <td data-label="Uploaded" className={styles.mutedCell}>
                {formatDateTime(document.uploaded_at)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default ReviewDocuments;