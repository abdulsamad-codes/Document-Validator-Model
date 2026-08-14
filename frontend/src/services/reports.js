import api from './api';

/**
 * Fetch the aggregated validation report for an application.
 *
 * The report is a read-only aggregation of stored pipeline results (documents,
 * OCR, extracted fields, business/technical validation and visual detections).
 * It returns 422 when the application has no validation results yet, which the
 * Validation Report page treats as an empty state.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<object>} The structured validation report.
 */
export function getValidationReport(applicationId) {
  return api
    .get(`/applications/${applicationId}/validation-report`)
    .then((response) => response.data);
}

/**
 * Build the download URL for the printable HTML validation report.
 *
 * The endpoint streams the same report rendered from a Jinja2 template; the
 * link is opened in a new tab (cookie auth, same origin).
 *
 * @param {number|string} applicationId Application id.
 * @returns {string} Absolute URL to the printable report.
 */
export function getValidationReportHtmlUrl(applicationId) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  return `${baseURL}/applications/${applicationId}/validation-report/html`;
}
