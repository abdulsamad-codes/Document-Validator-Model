import ValidationTaskRow from '../ValidationTaskRow/ValidationTaskRow';
import styles from './ValidationTaskTable.module.css';

/**
 * Table of validation tasks, ordered as returned by the queue endpoint
 * (status, then priority, then creation time) -- no client-side sorting.
 *
 * @param {object} props
 * @param {Array<object>} props.tasks Tasks to display.
 * @param {number|null} props.selectedTaskId Currently reviewed task id.
 * @param {Function} props.onSelect Callback invoked with a task id.
 */
function ValidationTaskTable({ tasks, selectedTaskId, onSelect }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Task ID</th>
            <th scope="col">Application</th>
            <th scope="col">Status</th>
            <th scope="col">Priority</th>
            <th scope="col">Created</th>
            <th scope="col" className={styles.actionsHeader}>
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <ValidationTaskRow
              key={task.id}
              task={task}
              selected={task.id === selectedTaskId}
              onSelect={onSelect}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default ValidationTaskTable;
