import StatusChip from '../../common/StatusChip/StatusChip';
import { getDocumentTypeConfig } from '../../../data/documents';
import { getRuleResultStatus } from '../../../data/statuses';
import { formatDateTime } from '../../../utils/format';
import styles from './ReviewDetections.module.css';

/**
 * Signature/stamp visual detection findings.
 *
 * Shows each stored detection outcome: the document, the detection type, and
 * whether the signature or stamp was present, with the detection confidence.
 *
 * @param {object} props
 * @param {object[]} props.detections The review screen's visual detections.
 */
function ReviewDetections({ detections }) {
  if (!detections || detections.length === 0) {
    return (
      <p className={styles.empty}>
        No signature or stamp detections are stored for this application.
      </p>
    );
  }

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">Document</th>
          <th scope="col">Detection</th>
          <th scope="col">Result</th>
          <th scope="col">Confidence</th>
          <th scope="col">Detected</th>
        </tr>
      </thead>
      <tbody>
        {detections.map((detection) => {
          const config = getDocumentTypeConfig(detection.document_type);
          const type = getRuleResultStatus(detection.detection_type);
          return (
            <tr key={`${detection.document_id}-${detection.detection_type}`}>
              <td data-label="Document" className={styles.typeCell}>
                {config.label}
              </td>
              <td data-label="Detection" className={styles.mutedCell}>
                {type.label}
              </td>
              <td data-label="Result">
                <StatusChip
                  label={detection.is_present ? 'Present' : 'Missing'}
                  variant={detection.is_present ? 'success' : 'danger'}
                />
              </td>
              <td data-label="Confidence" className={styles.mutedCell}>
                {detection.confidence != null
                  ? `${Math.round(detection.confidence * 100)}%`
                  : '—'}
              </td>
              <td data-label="Detected" className={styles.mutedCell}>
                {formatDateTime(detection.detected_at)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default ReviewDetections;