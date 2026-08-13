import api from './api';

/**
 * Fetch a paginated, optionally filtered page of the validation task queue.
 *
 * @param {object} [options]
 * @param {string} [options.status] Filter by task status.
 * @param {string} [options.priority] Filter by task priority.
 * @param {number} [options.offset] Number of tasks to skip.
 * @param {number} [options.limit] Maximum number of tasks to return.
 * @returns {Promise<{tasks: object[], total: number, offset: number, limit: number}>}
 */
export function listValidationTasks({ status, priority, offset = 0, limit = 50 } = {}) {
  return api
    .get('/validation/tasks', {
      params: { offset, limit, ...(status ? { status } : {}), ...(priority ? { priority } : {}) },
    })
    .then((response) => response.data);
}

/**
 * Fetch a single validation task.
 *
 * @param {number|string} taskId Task id.
 * @returns {Promise<object>} The task object.
 */
export function getValidationTask(taskId) {
  return api.get(`/validation/tasks/${taskId}`).then((response) => response.data);
}

/**
 * Create a validation task for an application.
 *
 * @param {object} payload
 * @param {number} payload.applicationId Application to validate.
 * @param {string} [payload.priority] Optional queue priority.
 * @returns {Promise<object>} The created task.
 */
export function createValidationTask({ applicationId, priority }) {
  return api
    .post('/validation/tasks', {
      application_id: applicationId,
      ...(priority ? { priority } : {}),
    })
    .then((response) => response.data);
}

/**
 * Move a PENDING task to IN_REVIEW.
 *
 * @param {number|string} taskId Task id.
 * @returns {Promise<object>} The updated task.
 */
export function startValidationTask(taskId) {
  return api.post(`/validation/tasks/${taskId}/start`).then((response) => response.data);
}

/**
 * Move an IN_REVIEW task to VALIDATED.
 *
 * @param {number|string} taskId Task id.
 * @param {string} [comment] Optional closing note.
 * @returns {Promise<object>} The updated task.
 */
export function completeValidationTask(taskId, comment) {
  return api
    .post(`/validation/tasks/${taskId}/complete`, { comment: comment || null })
    .then((response) => response.data);
}

/**
 * Move an IN_REVIEW task to REJECTED.
 *
 * @param {number|string} taskId Task id.
 * @param {string} reason Mandatory rejection reason.
 * @returns {Promise<object>} The updated task.
 */
export function rejectValidationTask(taskId, reason) {
  return api
    .post(`/validation/tasks/${taskId}/reject`, { reason })
    .then((response) => response.data);
}

/**
 * Move an IN_REVIEW task to NEEDS_CORRECTION.
 *
 * @param {number|string} taskId Task id.
 * @param {string} reason Mandatory correction reason.
 * @returns {Promise<object>} The updated task.
 */
export function requestValidationCorrection(taskId, reason) {
  return api
    .post(`/validation/tasks/${taskId}/request-correction`, { reason })
    .then((response) => response.data);
}

/**
 * Fetch the stored rule-engine + technical validation check results for a
 * task's application. Nothing is re-run.
 *
 * @param {number|string} taskId Task id.
 * @param {object} [options]
 * @param {number} [options.offset] Number of results to skip.
 * @param {number} [options.limit] Maximum number of results to return.
 * @returns {Promise<{results: object[], total: number, offset: number, limit: number}>}
 */
export function getValidationTaskResults(taskId, { offset = 0, limit = 50 } = {}) {
  return api
    .get(`/validation/tasks/${taskId}/results`, { params: { offset, limit } })
    .then((response) => response.data);
}

/**
 * Fetch the immutable audit log for a task, most recent first.
 *
 * @param {number|string} taskId Task id.
 * @param {object} [options]
 * @param {number} [options.offset] Number of log entries to skip.
 * @param {number} [options.limit] Maximum number of log entries to return.
 * @returns {Promise<{logs: object[], total: number, offset: number, limit: number}>}
 */
export function getValidationTaskLogs(taskId, { offset = 0, limit = 50 } = {}) {
  return api
    .get(`/validation/tasks/${taskId}/logs`, { params: { offset, limit } })
    .then((response) => response.data);
}

/**
 * Record a field verification event on an IN_REVIEW task.
 *
 * @param {number|string} fieldId Extracted field id.
 * @param {object} payload
 * @param {number} payload.taskId Task the event belongs to.
 * @param {string} payload.result Outcome (e.g. "CONFIRMED").
 * @param {string} [payload.comment] Optional free-form note.
 * @returns {Promise<object>} The created log entry.
 */
export function verifyValidationField(fieldId, { taskId, result, comment }) {
  return api
    .post(`/validation/fields/${fieldId}/verify`, {
      validation_task_id: taskId,
      result,
      comment: comment || null,
    })
    .then((response) => response.data);
}

/**
 * Record a field correction event on an IN_REVIEW task.
 *
 * @param {number|string} fieldId Extracted field id.
 * @param {object} payload
 * @param {number} payload.taskId Task the event belongs to.
 * @param {string} payload.correctedValue The corrected value.
 * @param {string} payload.reason Mandatory justification.
 * @returns {Promise<object>} The created log entry.
 */
export function correctValidationField(fieldId, { taskId, correctedValue, reason }) {
  return api
    .post(`/validation/fields/${fieldId}/correct`, {
      validation_task_id: taskId,
      corrected_value: correctedValue,
      reason,
    })
    .then((response) => response.data);
}

/**
 * Record a signature/stamp evidence review event on an IN_REVIEW task.
 *
 * @param {number|string} evidenceId Visual detection row id.
 * @param {object} payload
 * @param {number} payload.taskId Task the event belongs to.
 * @param {string} payload.result Outcome (e.g. "CONFIRMED").
 * @param {string} [payload.comment] Optional free-form note.
 * @returns {Promise<object>} The created log entry.
 */
export function reviewValidationEvidence(evidenceId, { taskId, result, comment }) {
  return api
    .post(`/validation/evidence/${evidenceId}/review`, {
      validation_task_id: taskId,
      result,
      comment: comment || null,
    })
    .then((response) => response.data);
}
