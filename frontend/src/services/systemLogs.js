import api from './api';

/**
 * Search the IT system log, newest first.
 *
 * Logs are operational audit records only -- never raw document contents or
 * extracted PII.
 *
 * @param {object} [filters]
 * @param {number} [filters.applicationId] Filter by application id.
 * @param {string} [filters.actor] Filter by actor name.
 * @param {string} [filters.eventType] Filter by event type / action.
 * @param {string} [filters.severity] Filter by severity.
 * @param {string} [filters.dateFrom] ISO date-time lower bound.
 * @param {string} [filters.dateTo] ISO date-time upper bound.
 * @param {string} [filters.query] Free-text search.
 * @param {object} [options]
 * @param {number} [options.offset] Number of entries to skip.
 * @param {number} [options.limit] Maximum number of entries to return.
 * @returns {Promise<{items: object[], total: number, offset: number, limit: number}>}
 */
export function searchSystemLogs(
  { applicationId, actor, eventType, severity, dateFrom, dateTo, query } = {},
  { offset = 0, limit = 50 } = {}
) {
  return api
    .get('/system-logs', {
      params: {
        offset,
        limit,
        ...(applicationId ? { application_id: applicationId } : {}),
        ...(actor ? { actor } : {}),
        ...(eventType ? { event_type: eventType } : {}),
        ...(severity ? { severity } : {}),
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
        ...(query ? { query } : {}),
      },
    })
    .then((response) => response.data);
}

/**
 * Fetch a single system log entry.
 *
 * @param {number|string} logId Log entry id.
 * @returns {Promise<object>} The system log entry.
 */
export function getSystemLog(logId) {
  return api.get(`/system-logs/${logId}`).then((response) => response.data);
}