import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

import ApplicationRow from '../ApplicationRow/ApplicationRow';
import styles from './ApplicationTable.module.css';

/**
 * Sortable columns and the field each one orders by. Exported so the
 * applications hook can reuse the same key space.
 */
export const SORTABLE_COLUMNS = [
  { key: 'id', label: 'Application ID' },
  { key: 'submitted_at', label: 'Submission Date' },
  { key: 'updated_at', label: 'Last Updated' },
];

/**
 * Table of applications with sortable columns.
 *
 * Renders a full table on desktop and collapses each row into a card on small
 * screens (see ApplicationRow). Column headers toggle sort order through
 * `onSortChange`; the active column reports its direction via `aria-sort`.
 *
 * @param {object} props
 * @param {Array<object>} props.applications Applications to display.
 * @param {string} props.sortKey Currently active sort field.
 * @param {'asc'|'desc'} props.sortDir Current sort direction.
 * @param {Function} props.onSortChange Callback with `(key, direction)`.
 */
function ApplicationTable({ applications, sortKey, sortDir, onSortChange }) {
  const toggleSort = (key) => {
    if (key === sortKey) {
      onSortChange(key, sortDir === 'asc' ? 'desc' : 'asc');
      return;
    }
    onSortChange(key, 'desc');
  };

  const ariaSortFor = (key) => {
    if (key !== sortKey) {
      return 'none';
    }
    return sortDir === 'asc' ? 'ascending' : 'descending';
  };

  const SortIcon = ({ column }) => {
    if (column !== sortKey) {
      return <ArrowUpDown aria-hidden="true" />;
    }
    return sortDir === 'asc' ? (
      <ArrowUp aria-hidden="true" />
    ) : (
      <ArrowDown aria-hidden="true" />
    );
  };

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {SORTABLE_COLUMNS.map((column) => (
              <th
                key={column.key}
                scope="col"
                aria-sort={ariaSortFor(column.key)}
              >
                <button
                  type="button"
                  className={styles.sortButton}
                  onClick={() => toggleSort(column.key)}
                >
                  {column.label}
                  <SortIcon column={column.key} />
                </button>
              </th>
            ))}
            <th scope="col">Status</th>
            <th scope="col">Created By</th>
            <th scope="col" className={styles.actionsHeader}>
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {applications.map((application) => (
            <ApplicationRow key={application.id} application={application} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default ApplicationTable;
