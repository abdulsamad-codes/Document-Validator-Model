import { Search, ShieldAlert, X } from 'lucide-react';

import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import Spinner from '../../components/common/Spinner/Spinner';
import StatusChip from '../../components/common/StatusChip/StatusChip';
import { useAuth } from '../../hooks/useAuth';
import { useSystemLogs } from '../../hooks/useSystemLogs';
import { humanizeEnum, formatDateTime } from '../../utils/format';
import { isIt } from '../../utils/roles';
import styles from './SystemLogsPage.module.css';

const SEVERITY_VARIANTS = {
  ERROR: 'danger',
  WARNING: 'warning',
  INFO: 'info',
};

/**
 * IT system log viewer.
 *
 * Reads the operational audit log through the IT-only backend API. The page is
 * reachable only through Settings -> Administration for IT users; non-IT users
 * see a professional access-denied state. The backend 403 remains the
 * authoritative gate -- this gate only decides what the UI shows.
 */
function SystemLogsPage() {
  const { user } = useAuth();
  const {
    entries,
    total,
    loading,
    error,
    filters,
    onFilterChange,
    onReset,
    onSearch,
  } = useSystemLogs();

  const allowed = isIt(user);

  if (!allowed) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <h2 className={styles.title}>System Logs</h2>
          <p className={styles.subtitle}>Operational audit records for the platform.</p>
        </header>
        <div className={styles.accessDenied} role="alert">
          <div className={styles.accessDeniedIcon} aria-hidden="true">
            <ShieldAlert />
          </div>
          <h3 className={styles.accessDeniedTitle}>Access denied</h3>
          <p className={styles.accessDeniedText}>
            System logs are restricted to the IT role. Your account is not authorized to view
            them. Contact your administrator if you believe this is in error.
          </p>
        </div>
      </div>
    );
  }

  const handleFilterChange = (key) => (event) => {
    onFilterChange(key, event.target.value);
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>System Logs</h2>
        <p className={styles.subtitle}>
          Search the operational audit trail: application events, account actions and system
          changes.
        </p>
      </header>

      <div className={styles.filters} aria-label="System log filters">
        <label className={styles.field} htmlFor="sl-query">
          <span className={styles.fieldLabel}>Search</span>
          <input
            id="sl-query"
            className={styles.input}
            type="search"
            value={filters.query}
            onChange={handleFilterChange('query')}
            placeholder="Match username, action or details"
          />
        </label>
        <label className={styles.field} htmlFor="sl-application">
          <span className={styles.fieldLabel}>Application</span>
          <input
            id="sl-application"
            className={styles.input}
            type="number"
            min="1"
            value={filters.applicationId}
            onChange={handleFilterChange('applicationId')}
            placeholder="Application id"
          />
        </label>
        <label className={styles.field} htmlFor="sl-actor">
          <span className={styles.fieldLabel}>Actor</span>
          <input
            id="sl-actor"
            className={styles.input}
            type="text"
            value={filters.actor}
            onChange={handleFilterChange('actor')}
            placeholder="Actor username"
          />
        </label>
        <label className={styles.field} htmlFor="sl-severity">
          <span className={styles.fieldLabel}>Severity</span>
          <select
            id="sl-severity"
            className={styles.input}
            value={filters.severity}
            onChange={handleFilterChange('severity')}
          >
            <option value="">All</option>
            <option value="ERROR">Error</option>
            <option value="WARNING">Warning</option>
            <option value="INFO">Info</option>
          </select>
        </label>
        <label className={styles.field} htmlFor="sl-date-from">
          <span className={styles.fieldLabel}>From</span>
          <input
            id="sl-date-from"
            className={styles.input}
            type="datetime-local"
            value={filters.dateFrom}
            onChange={handleFilterChange('dateFrom')}
          />
        </label>
        <label className={styles.field} htmlFor="sl-date-to">
          <span className={styles.fieldLabel}>To</span>
          <input
            id="sl-date-to"
            className={styles.input}
            type="datetime-local"
            value={filters.dateTo}
            onChange={handleFilterChange('dateTo')}
          />
        </label>
      </div>

      <div className={styles.toolbar}>
        <p className={styles.count} aria-live="polite">
          {total} {total === 1 ? 'entry' : 'entries'}
        </p>
        <button type="button" className={styles.searchBtn} onClick={onSearch}>
          <Search aria-hidden="true" />
          Search
        </button>
        <button type="button" className={styles.secondaryBtn} onClick={onReset}>
          <X aria-hidden="true" />
          Clear filters
        </button>
      </div>

      {loading ? (
        <div className={styles.loadingWrap} aria-busy="true">
          <Spinner size="medium" />
          <p className={styles.loadingText}>Loading system logs…</p>
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={onSearch} />
      ) : entries.length === 0 ? (
        <EmptyState
          title="No log entries"
          message="No audit records match the current filters."
        />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Actor</th>
                <th scope="col">Action</th>
                <th scope="col">Application</th>
                <th scope="col">Severity</th>
                <th scope="col">Details</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const severityVariant = SEVERITY_VARIANTS[entry.severity] ?? 'neutral';
                return (
                  <tr key={entry.id}>
                    <td data-label="When">{formatDateTime(entry.performed_at)}</td>
                    <td data-label="Actor">{entry.username}</td>
                    <td data-label="Action">{humanizeEnum(entry.action)}</td>
                    <td data-label="Application">
                      {entry.application_id != null ? `#${entry.application_id}` : '—'}
                    </td>
                    <td data-label="Severity">
                      {entry.severity ? (
                        <StatusChip
                          label={humanizeEnum(entry.severity)}
                          variant={severityVariant}
                        />
                      ) : (
                        '—'
                      )}
                    </td>
                    <td data-label="Details">
                      {entry.details ? JSON.stringify(entry.details) : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default SystemLogsPage;