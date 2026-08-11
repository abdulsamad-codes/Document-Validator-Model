import { useEffect } from 'react';

import { AlertTriangle } from 'lucide-react';
import Spinner from '../Spinner/Spinner';
import styles from './ConfirmDialog.module.css';

/**
 * Confirmation modal used before destructive actions (delete, replace).
 *
 * Renders nothing when closed. While `loading` is true the confirm button shows
 * a spinner and both actions are disabled. Pressing Escape cancels.
 *
 * @param {object} props
 * @param {boolean} props.open Whether the dialog is visible.
 * @param {string} props.title Heading text.
 * @param {string} props.message Body text.
 * @param {string} [props.confirmLabel] Confirm button label.
 * @param {string} [props.cancelLabel] Cancel button label.
 * @param {string} [props.tone] Visual tone: "danger" or "primary".
 * @param {boolean} [props.loading] Whether an action is in flight.
 * @param {Function} props.onConfirm Callback when confirmed.
 * @param {Function} props.onCancel Callback when dismissed.
 */
function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  loading = false,
  onConfirm,
  onCancel,
}) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !loading) {
        onCancel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, loading, onCancel]);

  if (!open) {
    return null;
  }

  return (
    <div className={styles.overlay} role="presentation" onMouseDown={onCancel}>
      <div
        className={styles.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className={styles.iconWrap} aria-hidden="true">
          <AlertTriangle />
        </div>
        <h3 id="confirm-title" className={styles.title}>
          {title}
        </h3>
        <p id="confirm-message" className={styles.message}>
          {message}
        </p>
        <div className={styles.actions}>
          <button
            className={styles.cancel}
            type="button"
            disabled={loading}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            className={`${styles.confirm} ${tone === 'danger' ? styles.danger : styles.primary}`}
            type="button"
            disabled={loading}
            onClick={onConfirm}
          >
            {loading && <Spinner size="small" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDialog;
