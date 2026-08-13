import { Eye } from 'lucide-react';

import { formatDateTime } from '../../../utils/format';
import { getValidationTaskStatus } from '../../../data/statuses';
import StatusChip from '../../common/StatusChip/StatusChip';
import styles from './ValidationTaskRow.module.css';

/**
 * A single validation task row in the operator dashboard queue table.
 *
 * On mobile the row collapses into a card, matching the ApplicationRow
 * pattern: table headers disappear and each cell renders its own
 * `data-label` beside the value.
 *
 * @param {object} props
 * @param {object} props.task Validation task to display.
 * @param {boolean} props.selected Whether this row is the active selection.
 * @param {Function} props.onSelect Callback invoked with the task id.
 */
function ValidationTaskRow({ task, selected, onSelect }) {
  const status = getValidationTaskStatus(task.status);

  return (
    <tr className={`${styles.row} ${selected ? styles.selected : ''}`}>
      <td className={styles.idCell} data-label="Task ID">
        #{task.id}
      </td>
      <td data-label="Application">#{task.application_id}</td>
      <td data-label="Status">
        <StatusChip label={status.label} variant={status.variant} />
      </td>
      <td data-label="Priority">{task.priority}</td>
      <td data-label="Created">{formatDateTime(task.created_at)}</td>
      <td className={styles.actionsCell} data-label="Actions">
        <button
          type="button"
          className={styles.actionButton}
          onClick={() => onSelect(task.id)}
          aria-label={`Review task ${task.id}`}
        >
          <Eye aria-hidden="true" />
          Review
        </button>
      </td>
    </tr>
  );
}

export default ValidationTaskRow;
