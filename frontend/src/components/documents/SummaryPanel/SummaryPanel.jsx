import { ArrowRight } from 'lucide-react';

import UploadProgress from '../UploadProgress/UploadProgress';
import { computeDocumentProgress } from '../../../data/documents';
import styles from './SummaryPanel.module.css';

/**
 * Right-hand summary panel for the upload page.
 *
 * Tracks how many of the required document copies have been uploaded and gates
 * the "Continue" action until every slot is filled. The session tally reports
 * how many files were uploaded or failed during this visit so the employee gets
 * immediate confirmation of their work before moving on.
 *
 * @param {object} props
 * @param {Array<object>} props.documents Uploaded documents.
 * @param {{uploaded: number, failed: number}} props.sessionTally Files
 *   uploaded or failed during this session.
 * @param {Function} props.onContinue Callback fired when Continue is clicked.
 */
function SummaryPanel({ documents, sessionTally, onContinue }) {
  const { totalCopies, uploadedCopies, percent } = computeDocumentProgress(documents);
  const remaining = Math.max(0, totalCopies - uploadedCopies);
  const ready = remaining === 0;
  const { uploaded: sessionUploaded, failed: sessionFailed } = sessionTally;
  const hasSessionActivity = sessionUploaded > 0 || sessionFailed > 0;

  return (
    <aside className={styles.panel}>
      <h3 className={styles.title}>Upload Summary</h3>

      <div className={styles.counts}>
        <div className={styles.count}>
          <span className={styles.countValue}>{uploadedCopies}</span>
          <span className={styles.countLabel}>Uploaded</span>
        </div>
        <div className={styles.count}>
          <span className={styles.countValue}>{remaining}</span>
          <span className={styles.countLabel}>Remaining</span>
        </div>
      </div>

      <UploadProgress progress={percent} label={`${percent}% complete`} />

      {hasSessionActivity && (
        <p className={styles.session}>
          Uploaded successfully: {sessionUploaded}
          {sessionFailed > 0 && <span className={styles.sessionFailed}> · Failed: {sessionFailed}</span>}
        </p>
      )}

      <p className={styles.note}>
        {ready
          ? 'All required documents have been uploaded.'
          : `Upload ${remaining} more required copy${remaining === 1 ? '' : 'ies'} to continue.`}
      </p>

      <button
        className={styles.continue}
        type="button"
        disabled={!ready}
        onClick={onContinue}
      >
        Continue to Document Completeness
        <ArrowRight aria-hidden="true" />
      </button>
    </aside>
  );
}

export default SummaryPanel;
