import { CheckCircle2, Fingerprint, Stamp } from 'lucide-react';
import styles from './ReportVisual.module.css';

function Stat({ label, value }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}

/**
 * Signature/stamp visual evidence summary.
 *
 * Renders the aggregated detection totals stored by the pipeline: how many
 * documents were checked and how many had signatures and stamps present or
 * missing.
 *
 * @param {object} props
 * @param {object|null} props.visual The report's visual detection summary.
 */
function ReportVisual({ visual }) {
  if (!visual) {
    return (
      <p className={styles.empty}>
        No visual evidence results are available for this application.
      </p>
    );
  }

  return (
    <div className={styles.grid}>
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.iconWrap} aria-hidden="true">
            <Fingerprint />
          </div>
          <h4 className={styles.cardTitle}>Signatures</h4>
        </div>
        <div className={styles.stats}>
          <Stat value={visual.signature_detected ?? 0} label="Present" />
          <Stat value={visual.signature_missing ?? 0} label="Missing" />
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.iconWrap} aria-hidden="true">
            <Stamp />
          </div>
          <h4 className={styles.cardTitle}>Stamps</h4>
        </div>
        <div className={styles.stats}>
          <Stat value={visual.stamp_detected ?? 0} label="Present" />
          <Stat value={visual.stamp_missing ?? 0} label="Missing" />
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.iconWrap} aria-hidden="true">
            <CheckCircle2 />
          </div>
          <h4 className={styles.cardTitle}>Documents Checked</h4>
        </div>
        <div className={styles.stats}>
          <Stat value={visual.documents_checked ?? 0} label="Verified" />
        </div>
      </div>
    </div>
  );
}

export default ReportVisual;