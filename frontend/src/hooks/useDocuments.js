import { useCallback, useEffect, useMemo, useState } from 'react';

import { replaceDocument, uploadDocument } from '../services/documents';
import { deleteDocument } from '../services/documents';
import { getApiErrorMessage } from '../utils/apiError';
import { useApplicationsStore } from '../store/ApplicationsContext';

/**
 * Load and manage the documents of a single application.
 *
 * A thin consumer of the shared applications store, so the dashboard checklist
 * and the upload page always see the same document state. `pending` maps a
 * document id to its in-flight operation so each slot can render an
 * "Uploading" state with a live progress bar. Action functions never throw;
 * they return `{ ok, error?, document? }` so the page owns toasts and
 * confirmations.
 *
 * @param {number|string} applicationId Application id.
 */
export function useDocuments(applicationId) {
  const { documentsByApplication, loadDocuments, setDocumentItems } = useApplicationsStore();
  const [pending, setPending] = useState({});

  const state = documentsByApplication[applicationId] ?? {};
  const { items: documents = [], loading = true, error = null } = state;

  const reload = useCallback(() => loadDocuments(applicationId), [applicationId, loadDocuments]);

  useEffect(() => {
    reload();
  }, [reload]);

  const setPendingProgress = (documentId, progress) => {
    setPending((prev) => ({ ...prev, [documentId]: { ...prev[documentId], progress } }));
  };

  const clearPending = (documentId) => {
    setPending((prev) => {
      const next = { ...prev };
      delete next[documentId];
      return next;
    });
  };

  const findDocument = useCallback(
    (documentType, copyNumber) =>
      documents.find(
        (document) =>
          document.document_type === documentType &&
          (copyNumber === undefined || document.copy_number === copyNumber)
      ),
    [documents]
  );

  const upsertDocument = useCallback(
    (document) => {
      setDocumentItems(applicationId, [
        ...documents.filter((doc) => doc.id !== document.id),
        document,
      ]);
    },
    [applicationId, documents, setDocumentItems]
  );

  /**
   * Upload a new file into a specific copy slot, or replace the file already
   * occupying that slot.
   *
   * @param {object} params
   * @param {string} params.documentType Backend document type value.
   * @param {number} params.copyNumber 1-based copy slot within the type.
   * @param {File} params.file The selected file.
   */
  const uploadToSlot = useCallback(
    async ({ documentType, copyNumber, file }) => {
      const existing = findDocument(documentType, copyNumber);
      const operationKey = existing ? `replace-${existing.id}` : `upload-${documentType}-${copyNumber}`;
      setPending((prev) => ({
        ...prev,
        [operationKey]: { phase: existing ? 'replace' : 'upload', progress: 0 },
      }));

      const onUploadProgress = (event) => {
        if (event.total) {
          setPendingProgress(operationKey, Math.round((event.loaded / event.total) * 100));
        }
      };

      try {
        const document = existing
          ? await replaceDocument({
              applicationId,
              documentId: existing.id,
              documentType,
              file,
              onUploadProgress,
            })
          : await uploadDocument({
              applicationId,
              documentType,
              copyNumber,
              file,
              onUploadProgress,
            });

        clearPending(operationKey);
        upsertDocument(document);
        return { ok: true, document };
      } catch (err) {
        clearPending(operationKey);
        return { ok: false, error: getApiErrorMessage(err) };
      }
    },
    [applicationId, documents, findDocument, upsertDocument]
  );

  const removeDocument = useCallback(
    async (document) => {
      try {
        await deleteDocument({ applicationId, documentId: document.id });
        setDocumentItems(
          applicationId,
          documents.filter((doc) => doc.id !== document.id)
        );
        return { ok: true };
      } catch (err) {
        return { ok: false, error: getApiErrorMessage(err) };
      }
    },
    [applicationId, documents, setDocumentItems]
  );

  const documentsOfType = useCallback(
    (documentType) =>
      documents
        .filter((document) => document.document_type === documentType)
        .sort((a, b) => a.copy_number - b.copy_number),
    [documents]
  );

  const uploadBulk = useCallback(
    async (file) => {
      const operationKey = 'upload-bulk';
      setPending((prev) => ({
        ...prev,
        [operationKey]: { phase: 'upload', progress: 0 },
      }));

      const onUploadProgress = (event) => {
        if (event.total) {
          setPendingProgress(operationKey, Math.round((event.loaded / event.total) * 100));
        }
      };

      try {
        const { uploadBulkDocument } = await import('../services/documents');
        const response = await uploadBulkDocument({
          applicationId,
          file,
          onUploadProgress,
        });

        clearPending(operationKey);
        // We reload all documents so the newly extracted copies appear in the list.
        await reload();
        return { ok: true, data: response };
      } catch (err) {
        clearPending(operationKey);
        return { ok: false, error: getApiErrorMessage(err) };
      }
    },
    [applicationId, reload]
  );

  return useMemo(
    () => ({
      documents,
      loading,
      error,
      reload,
      pending,
      findDocument,
      documentsOfType,
      uploadToSlot,
      removeDocument,
      uploadBulk,
    }),
    [documents, loading, error, reload, pending, findDocument, documentsOfType, uploadToSlot, removeDocument, uploadBulk]
  );
}
