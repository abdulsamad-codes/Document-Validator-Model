import { Download, FileText, RefreshCw, Trash2, UploadCloud } from 'lucide-react';

import Spinner from '../../common/Spinner/Spinner';
import StatusChip from '../../common/StatusChip/StatusChip';
import UploadProgress from '../UploadProgress/UploadProgress';
import { getDocumentStatus } from '../../../data/statuses';
import { getDocumentDownloadUrl } from '../../../services/documents';
import styles from './DocumentRow.module.css';

/**
 * One row in the document list.
 *
 * Shows the document name, a status chip (Uploaded / Uploading / Missing /
 * Failed), the uploaded filename and the contextual actions. Upload is shown
 * when the document is missing or failed; Replace and Delete are shown when a
 * document exists. While an upload is in flight the actions are replaced by a
 * live progress bar; while a delete is in flight the actions stay visible but
 * disabled, with the Delete button showing a spinner, so a second click can't
 * fire a duplicate request.
 *
 * @param {object} props
 * @param {object} props.entry Document catalogue entry (label, type).
 * @param {object|null} props.document Uploaded document metadata, or null.
 * @param {object|null} props.pending In-flight upload state, or null.
 * @param {boolean} [props.isDeleting] Whether a delete request is in flight.
 * @param {Function} props.onUpload Triggered to upload a missing document.
 * @param {Function} props.onReplace Triggered to replace an existing document.
 * @param {Function} props.onDelete Triggered to delete an existing document.
 */
function DocumentRow({
  entry,
  document,
  pending,
  isDeleting = false,
  onUpload,
  onReplace,
  onDelete,
}) {
  const statusConfig = getDocumentStatus(pending ? 'UPLOADING' : document?.processing_status ?? 'MISSING');
  const hasDocument = Boolean(document);
  const isUploading = Boolean(pending);
  const actionsDisabled = isUploading || isDeleting;

  return (
    <li className={`${styles.row} ${isUploading ? styles.rowUploading : ''}`}>
      <div className={styles.main}>
        <div className={styles.iconWrap} aria-hidden="true">
          <FileText />
        </div>
        <div className={styles.meta}>
          <span className={styles.name}>{entry.label}</span>
          <span className={styles.filename}>
            {document?.original_filename ?? (isUploading ? 'Uploading file...' : 'Not uploaded yet')}
          </span>
        </div>
        <StatusChip label={statusConfig.label} variant={statusConfig.variant} />
      </div>

      {isUploading ? (
        <UploadProgress progress={pending.progress ?? 0} />
      ) : (
        <div className={styles.actions}>
          {!hasDocument && (
            <button
              className={styles.uploadBtn}
              type="button"
              onClick={onUpload}
              disabled={actionsDisabled}
            >
              <UploadCloud aria-hidden="true" />
              Upload
            </button>
          )}
          {hasDocument && (
            <>
              <a
                className={styles.downloadBtn}
                href={getDocumentDownloadUrl(document.id)}
                aria-label={`Download ${entry.label}`}
                aria-disabled={actionsDisabled}
                onClick={(event) => {
                  if (actionsDisabled) {
                    event.preventDefault();
                  }
                }}
              >
                <Download aria-hidden="true" />
                Download
              </a>
              <button
                className={styles.replaceBtn}
                type="button"
                onClick={onReplace}
                disabled={actionsDisabled}
              >
                <RefreshCw aria-hidden="true" />
                Replace
              </button>
              <button
                className={styles.deleteBtn}
                type="button"
                onClick={onDelete}
                disabled={actionsDisabled}
                aria-label={isDeleting ? `Deleting ${entry.label}` : `Delete ${entry.label}`}
              >
                {isDeleting ? <Spinner /> : <Trash2 aria-hidden="true" />}
                {isDeleting ? 'Deleting…' : 'Delete'}
              </button>
            </>
          )}
        </div>
      )}
    </li>
  );
}

export default DocumentRow;
