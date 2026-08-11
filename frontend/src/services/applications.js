import api from './api';

/**
 * Fetch a paginated list of applications, optionally filtered by status.
 *
 * @param {object} [options]
 * @param {number} [options.offset] Number of applications to skip.
 * @param {number} [options.limit] Maximum number of applications to return.
 * @param {string} [options.status] Backend application status to filter by.
 * @returns {Promise<{items: object[], total: number}>}
 */
export function listApplications({ offset = 0, limit = 50, status } = {}) {
  return api
    .get('/applications', { params: { offset, limit, ...(status ? { status } : {}) } })
    .then((response) => response.data);
}

/**
 * Fetch a single application.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<object>} The application object.
 */
export function getApplication(applicationId) {
  return api.get(`/applications/${applicationId}`).then((response) => response.data.application);
}

/**
 * Create a new application.
 *
 * @param {object} payload
 * @param {string} payload.createdBy Identifier of the submitting user.
 * @param {string} [payload.notes] Optional free-form notes.
 * @returns {Promise<object>} The created application object.
 */
export function createApplication({ createdBy, notes }) {
  return api
    .post('/applications', { created_by: createdBy, notes: notes || null })
    .then((response) => response.data.application);
}
