import { Info } from 'lucide-react';

import ApplicationStatusBadge from '../../applications/ApplicationStatusBadge/ApplicationStatusBadge';
import StatusChip from '../../common/StatusChip/StatusChip';
import { getVerificationStatus } from '../../../data/statuses';
import { formatDateTime } from '../../../utils/format';
import styles from './ReviewSummary.module.css';

/**
 * Application header for the final review.
 *
 * Shows the static application information, the overall validation verdict and
 * the report recommendations that guide the reviewer's decision.
 *
 * @param {object} props
 * @param {object} reviewScreen The review screen payload.
 */
function ReviewSummary({ reviewScreen }) {
  const { application, report } = reviewScreen;
  const overall = getVerificationStatus(report?.overall_status);
  const recommendations = report?.recommendations ?? [];

  return (
    <div className={styles.summary}>
      <div className={styles.top}>
        <div className={styles.identity}>
          <h3 className={styles.name}>Application #{application.application_id}</h3>
          <div className={styles.meta}>
            <ApplicationStatusBadge status={application.status} />
            <span>Submitted {formatDateTime(application.submitted_at)}</span>
            <span>Submitted by {application.created_by}</span>
            <span>Updated {formatDateTime(application.updated_at)}</span>
          </div>
        </div>
        <div className={styles.verdict}>
          <span className={styles.verdictLabel}>Overall status</span>
          <StatusChip label={overall.label} variant={overall.variant} />
        </div>
      </div>

      {recommendations.length > 0 && (
        <div className={styles.recommendations}>
          <div className={styles.recHeader}>
            <Info className={styles.recIcon} aria-hidden="true" />
            <h4 className={styles.recTitle}>Recommendations</h4>
          </div>
          <ul className={styles.recList}>
            {recommendations.map((rec) => (
              <li key={rec.code}>{rec.message}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default ReviewSummary;