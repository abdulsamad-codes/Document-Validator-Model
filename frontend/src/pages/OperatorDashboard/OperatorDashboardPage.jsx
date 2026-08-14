import { useState } from 'react';

import ErrorState from '../../components/common/ErrorState/ErrorState';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import ValidationTaskDetailPanel from '../../components/validation/ValidationTaskDetailPanel/ValidationTaskDetailPanel';
import ValidationTaskTable from '../../components/validation/ValidationTaskTable/ValidationTaskTable';
import { VALIDATION_TASK_STATUSES } from '../../data/statuses';
import { useValidationTasks } from '../../hooks/useValidationTasks';
import styles from './OperatorDashboardPage.module.css';

/**
 * Operator dashboard: the validation task queue plus a review panel.
 *
 * Lists every validation task across all applications (filterable by
 * status), and opens an inline review panel for the selected task where the
 * operator drives the task lifecycle (start / complete / reject /
 * request-correction) against the stored rule-engine results and audit log.
 */
function OperatorDashboardPage() {
  const { tasks, total, loading, error, reload, statusFilter, onStatusChange } =
    useValidationTasks();
  const [selectedTaskId, setSelectedTaskId] = useState(null);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>Validation Tasks</h2>
          <p className={styles.subtitle}>
            Review validation tasks and drive them through approval, rejection or correction.
          </p>
        </div>
      </header>

      <div className={styles.toolbar}>
        <label className={styles.filter} htmlFor="task-status-filter">
          <span className={styles.filterLabel}>Status</span>
          <select
            id="task-status-filter"
            className={styles.select}
            value={statusFilter}
            onChange={(event) => onStatusChange(event.target.value)}
            aria-label="Filter validation tasks by status"
          >
            <option value="">All</option>
            {VALIDATION_TASK_STATUSES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <p className={styles.count} aria-live="polite">
          {total} {total === 1 ? 'task' : 'tasks'}
        </p>
      </div>

      {loading ? (
        <p className={styles.loadingText}>Loading queue…</p>
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : tasks.length === 0 ? (
        <EmptyState
          title="No validation tasks"
          message={
            statusFilter
              ? 'No tasks match this status filter.'
              : 'No validation tasks have been created yet.'
          }
        />
      ) : (
        <ValidationTaskTable
          tasks={tasks}
          selectedTaskId={selectedTaskId}
          onSelect={setSelectedTaskId}
        />
      )}

      {selectedTaskId && (
        <ValidationTaskDetailPanel
          taskId={selectedTaskId}
          onClose={() => setSelectedTaskId(null)}
          onQueueChange={reload}
        />
      )}
    </div>
  );
}

export default OperatorDashboardPage;
