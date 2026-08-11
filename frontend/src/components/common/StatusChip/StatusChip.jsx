import styles from './StatusChip.module.css';

/**
 * Coloured pill that renders a status value (application or document status).
 *
 * The caller resolves the raw status via `getApplicationStatus` /
 * `getDocumentStatus` and passes the display label + variant through, keeping
 * this component purely presentational.
 *
 * @param {object} props
 * @param {string} props.label Display text, e.g. "Uploaded".
 * @param {string} props.variant Chip colour: "success", "warning", "danger",
 *   "info" or "neutral".
 */
function StatusChip({ label, variant = 'neutral' }) {
  return (
    <span className={`${styles.chip} ${styles[variant] ?? styles.neutral}`}>
      <span className={styles.dot} aria-hidden="true" />
      {label}
    </span>
  );
}

export default StatusChip;
