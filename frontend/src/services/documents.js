import api from './api';

/**
 * Build a multipart form body for a document upload request.
 *
 * The backend expects two fields: `file` (the binary) and `document_type` (the
 * backend enum value).
 *
 * @param {object} params
 * @param {string} params.documentType Backend document type value.
 * @param {File} params.file The selected file.
 * @returns {FormData}
 */
function buildFormData({ documentType, copyNumber, file }) {
  const formData = new FormData();
  formData.append('document_type', documentType);
  if (copyNumber !== undefined) {
    formData.append('copy_number', String(copyNumber));
  }
  formData.append('file', file);
  return formData;
}

/**
 * List the documents belonging to an application.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<{items: object[], total: number}>}
 */
export function listDocuments(applicationId) {
  return api.get(`/applications/${applicationId}/documents`).then((response) => response.data);
}

/**
 * Upload a new document for an application.
 *
 * @param {object} params
 * @param {number|string} params.applicationId Application id.
 * @param {string} params.documentType Backend document type value.
 * @param {File} params.file The selected file.
 * @param {Function} [params.onUploadProgress] Axios upload progress callback.
 * @returns {Promise<object>} The uploaded document metadata.
 */
export function uploadDocument({ applicationId, documentType, copyNumber, file, onUploadProgress }) {
  return api
    .post(
      `/applications/${applicationId}/documents`,
      buildFormData({ documentType, copyNumber, file }),
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress,
      }
    )
    .then((response) => response.data.document);
}

/**
 * Upload a bulk PDF to be split into individual documents.
 *
 * @param {object} params
 * @param {number|string} params.applicationId Application id.
 * @param {File} params.file The selected bulk PDF file.
 * @param {Function} [params.onUploadProgress] Axios upload progress callback.
 * @returns {Promise<object>} The bulk upload response (including extracted documents).
 */
export function uploadBulkDocument({ applicationId, file, onUploadProgress }) {
  const formData = new FormData();
  formData.append('file', file);
  return api
    .post(
      `/applications/${applicationId}/bulk-upload`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress,
      }
    )
    .then((response) => response.data);
}

/**
 * Replace an existing document for an application.
 *
 * @param {object} params
 * @param {number|string} params.applicationId Application id.
 * @param {number|string} params.documentId Document id to replace.
 * @param {string} params.documentType Backend document type value.
 * @param {File} params.file The replacement file.
 * @param {Function} [params.onUploadProgress] Axios upload progress callback.
 * @returns {Promise<object>} The replacement document metadata.
 */
export function replaceDocument({ applicationId, documentId, documentType, file, onUploadProgress }) {
  return api
    .put(
      `/applications/${applicationId}/documents/${documentId}`,
      buildFormData({ documentType, file }),
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress,
      }
    )
    .then((response) => response.data.document);
}

/**
 * Delete a document belonging to an application.
 *
 * @param {object} params
 * @param {number|string} params.applicationId Application id.
 * @param {number|string} params.documentId Document id to delete.
 * @returns {Promise<void>}
 */
export function deleteDocument({ applicationId, documentId }) {
  return api.delete(`/applications/${applicationId}/documents/${documentId}`).then(() => undefined);
}

/**
 * Build the download URL for a document.
 *
 * The endpoint streams the original file with an attachment filename, so the
 * download works from a plain anchor (cookie auth, same origin). The internal
 * storage path stays on the server; only the public endpoint is exposed here.
 *
 * @param {number|string} documentId Document id.
 * @returns {string} Absolute download URL.
 */
export function getDocumentDownloadUrl(documentId) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  return `${baseURL}/documents/${documentId}/download`;
}
