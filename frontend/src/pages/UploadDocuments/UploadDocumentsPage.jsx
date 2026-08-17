import { useState, useEffect } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ArrowLeft } from 'lucide-react';

import ConfirmDialog from '../../components/common/ConfirmDialog/ConfirmDialog';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import Spinner from '../../components/common/Spinner/Spinner';
import { useToast } from '../../components/common/Toast/ToastContext';
import BulkUploadZone from '../../components/documents/BulkUploadZone/BulkUploadZone';
import DocumentList from '../../components/documents/DocumentList/DocumentList';
import SummaryPanel from '../../components/documents/SummaryPanel/SummaryPanel';
import { useDocuments } from '../../hooks/useDocuments';
import { getPreference } from '../../utils/preferences';
import { startProcessing } from '../../services/processing';
import { REQUIRED_DOCUMENT_TYPES } from '../../data/documents';
import styles from './UploadDocumentsPage.module.css';

/**
 * Document upload page for one application.
 *
 * Left column holds the fixed slot checklist; right column holds the summary
 * panel. Each required category shows its exact number of numbered slots;
 * choosing a file for a slot uploads (or replaces) exactly that slot. Uploading
 * and deleting are confirmed, toasted and surfaced via the documents hook, and
 * the shared store keeps the dashboard checklist in sync. "Continue to Document
 * Completeness" opens the completeness module once all required copies exist.
 */
function UploadDocumentsPage() {
  const { applicationId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const { documents, loading, error, reload, pending, findDocument, uploadToSlot, removeDocument, uploadBulk } =
    useDocuments(applicationId);

  const [deleteConfirmDocument, setDeleteConfirmDocument] = useState(null);
  const [sessionTally, setSessionTally] = useState({ uploaded: 0, failed: 0 });

  const pendingBulkDocument = documents?.find(
    (d) => d.document_type === 'BULK_UPLOAD' && d.processing_status !== 'COMPLETED'
  );

  useEffect(() => {
    if (pendingBulkDocument) {
      const timer = setInterval(() => {
        reload();
      }, 5000);
      return () => clearInterval(timer);
    }
  }, [pendingBulkDocument, reload]);

  const handleBulkUpload = async (file) => {
    const result = await uploadBulk(file);
    if (result.ok) {
      toast.success('Bulk PDF uploaded and split successfully.');
      maybeAutoStartProcessing();
    } else {
      toast.error(result.error);
    }
  };

  const handleUpload = async (documentType, copyNumber, file, validationError) => {
    if (!file) {
      if (validationError) {
        setSessionTally((prev) => ({ ...prev, failed: prev.failed + 1 }));
        toast.error(validationError);
      }
      return;
    }
    const result = await uploadToSlot({ documentType, copyNumber, file });
    if (result.ok) {
      setSessionTally((prev) => ({ ...prev, uploaded: prev.uploaded + 1 }));
      toast.success(`Copy ${copyNumber} uploaded successfully.`);
      maybeAutoStartProcessing();
    } else {
      setSessionTally((prev) => ({ ...prev, failed: prev.failed + 1 }));
      toast.error(result.error);
    }
  };

  const deleteDocument = async (document) => {
    const result = await removeDocument(document);
    if (result.ok) {
      toast.success('Document deleted successfully.');
    } else {
      toast.error(result.error);
    }
  };

  const handleDeleteConfirmed = () => {
    const document = deleteConfirmDocument;
    setDeleteConfirmDocument(null);
    if (document) {
      void deleteDocument(document);
    }
  };

  const handleDeleteRequest = (document) => {
    if (getPreference('confirmBeforeDeleteDocument', true)) {
      setDeleteConfirmDocument(document);
      return;
    }
    void deleteDocument(document);
  };

  const maybeAutoStartProcessing = () => {
    if (!getPreference('autoStartProcessingAfterUpload', true)) {
      return;
    }
    startProcessing(applicationId).catch(() => {
      // Best effort: a processing failure should never surface as an upload error.
    });
  };

  if (loading) {
    return (
      <div className={styles.center} aria-busy="true">
        <Spinner size="medium" />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <Link to={`/applications/${applicationId}`} className={styles.backLink}>
        <ArrowLeft aria-hidden="true" />
        Back to Application #{applicationId}
      </Link>

      <header className={styles.header}>
        <h2 className={styles.title}>Upload Documents</h2>
        <p className={styles.subtitle}>
          Attach the required files for application #{applicationId}.
        </p>
      </header>

      {error ? (
        <ErrorState message="Unable to load documents." onRetry={reload} />
      ) : (
        <div className={styles.layout}>
          <div className={styles.main}>
            {pendingBulkDocument ? (
              <div className={styles.processingBanner}>
                <Spinner size="small" />
                <p>Your combined PDF is being split and analyzed in the background. This may take a few minutes...</p>
              </div>
            ) : (
              <BulkUploadZone
                onUpload={handleBulkUpload}
                pending={pending['upload-bulk']}
              />
            )}
            <DocumentList
              requiredTypes={REQUIRED_DOCUMENT_TYPES}
              findDocument={findDocument}
              pending={pending}
              onUpload={handleUpload}
              onDelete={handleDeleteRequest}
            />
          </div>

          <SummaryPanel
            documents={documents}
            sessionTally={sessionTally}
            onContinue={() => navigate('/completeness')}
          />
        </div>
      )}

      <ConfirmDialog
        open={deleteConfirmDocument !== null}
        title="Delete this document?"
        message={`"${deleteConfirmDocument?.original_filename}" will be permanently removed from application #${applicationId}.`}
        confirmLabel="Delete"
        tone="danger"
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeleteConfirmDocument(null)}
      />
    </div>
  );
}

export default UploadDocumentsPage;
