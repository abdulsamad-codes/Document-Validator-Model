import { Eye, UploadCloud } from 'lucide-react';
import { Link } from 'react-router-dom';

import { formatDate } from '../../../utils/format';
import ApplicationStatusBadge from '../ApplicationStatusBadge/ApplicationStatusBadge';
import styles from './ApplicationRow.module.css';

/**
 * A single application row in the applications table.
 *
 * On mobile the row collapses into a card: the table headers disappear and
 * each cell renders its own `data-label` beside the value, so the table keeps
 * one markup source for every breakpoint.
 *
 * @param {object} props
 * @param {object} props.application Application object to display.
 */
function ApplicationRow({ application }) {
  return (
    <tr className={styles.row}>
      <td className={styles.idCell} data-label="Application ID">
        <Link to={`/applications/${application.id}`} className={styles.idLink}>
          #{application.id}
        </Link>
      </td>
      <td data-label="Status">
        <ApplicationStatusBadge status={application.status} />
      </td>
      <td data-label="Submission Date">{formatDate(application.submitted_at)}</td>
      <td data-label="Last Updated">{formatDate(application.updated_at)}</td>
      <td data-label="Created By">{application.created_by}</td>
      <td className={styles.actionsCell} data-label="Actions">
        <div className={styles.actions}>
          <Link
            to={`/applications/${application.id}`}
            className={styles.actionLink}
            aria-label={`View application ${application.id}`}
          >
            <Eye aria-hidden="true" />
            View
          </Link>
          <Link
            to={`/applications/${application.id}/upload`}
            className={styles.actionLink}
            aria-label={`Upload documents for application ${application.id}`}
          >
            <UploadCloud aria-hidden="true" />
            Upload Documents
          </Link>
        </div>
      </td>
    </tr>
  );
}

export default ApplicationRow;
