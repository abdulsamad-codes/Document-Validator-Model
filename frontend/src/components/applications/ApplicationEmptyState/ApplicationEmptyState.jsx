import { Link } from 'react-router-dom';

import { Plus } from 'lucide-react';

import EmptyState from '../../common/EmptyState/EmptyState';
import styles from './ApplicationEmptyState.module.css';

/**
 * Empty state for the applications list.
 *
 * When the list is genuinely empty it invites the employee to create the first
 * application. When search or filters hide every row, it suggests relaxing
 * them instead.
 *
 * @param {object} props
 * @param {boolean} [props.filtered] True when filters/search caused the empty
 *   result, so the create-action copy is suppressed.
 */
function ApplicationEmptyState({ filtered = false }) {
  return (
    <div className={styles.wrap}>
      {filtered ? (
        <EmptyState
          title="No applications found"
          message="No applications match the current search or filters."
        />
      ) : (
        <EmptyState
          title="No applications yet"
          message="Create an application to begin document verification."
          action={
            <Link to="/applications/new" className={styles.createBtn}>
              <Plus aria-hidden="true" />
              Create Application
            </Link>
          }
        />
      )}
    </div>
  );
}

export default ApplicationEmptyState;
