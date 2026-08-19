import { useRef } from 'react';
import { ClipboardList } from 'lucide-react';

import DocumentRow from '../DocumentRow/DocumentRow';
import { validateUploadFile } from '../../../data/documents';
import styles from './DocumentList.module.css';

/**
 * Fixed slot checklist for an application's required documents.
 *
 * Each required category renders its exact number of numbered slots
 * (Copy 1 … Copy N). Empty slots stay visible with an Upload action; occupied
 * slots offer Download, Replace and Delete. A category header shows its copy
 * progress (e.g. "1-Link Application Form · 2/3").
 *
 * @param {object} props
 * @param {Array<object>} props.requiredTypes Required document catalogue entries.
 * @param {Function} props.findDocument Lookup document metadata by type + copy.
 * @param {object} props.pending Map of slot key to in-flight upload state.
 * @param {Function} props.onUpload Handler for uploading into a slot.
 * @param {Function} props.onDelete Handler for deleting an existing document.
 */
function DocumentList({
  requiredTypes,
  findDocument,
  pending,
  onUpload,
  onDelete,
}) {
  const fileInputs = useRef({});

  const triggerPicker = (type, copyNumber) => {
    const input = fileInputs.current[`${type}-${copyNumber}`];
    if (input) {
      input.value = '';
      input.click();
    }
  };

  const handleFile = async (type, copyNumber, event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const validationError = validateUploadFile(file);
    if (validationError) {
      onUpload(type, copyNumber, null, validationError);
      return;
    }
    onUpload(type, copyNumber, file, null);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.iconWrap} aria-hidden="true">
          <ClipboardList />
        </div>
        <div>
          <h3 className={styles.title}>Document Checklist</h3>
          <p className={styles.subtitle}>
            Upload each required copy. Every slot accepts a single file.
          </p>
        </div>
      </div>

      <div className={styles.groups}>
        {requiredTypes.map((entry) => {
          const present = Array.from({ length: entry.requiredCopies }, (_, index) => {
            const slotType = entry.slotTypes?.[index] ?? entry.type;
            return findDocument(slotType, entry.slotTypes ? 1 : index + 1);
          }).filter(Boolean).length;
          return (
            <section key={entry.type} className={styles.group}>
              <div className={styles.groupHeader}>
                <h4 className={styles.groupTitle}>{entry.label}</h4>
                <span className={styles.groupCount}>
                  {present} / {entry.requiredCopies}
                </span>
              </div>
              <ul className={styles.grid}>
                {Array.from({ length: entry.requiredCopies }, (_, index) => {
                  const slotType = entry.slotTypes?.[index] ?? entry.type;
                  const copyNumber = entry.slotTypes ? 1 : index + 1;
                  const slotKey = `${slotType}-${copyNumber}`;
                  const slotLabel = entry.slotLabels?.[index] ?? `Copy ${index + 1}`;
                  const document = findDocument(slotType, copyNumber);
                  const slotPending =
                    pending[`upload-${slotKey}`] ?? (document ? pending[`replace-${document.id}`] : null);
                  const isDeleting = document ? Boolean(pending[`delete-${document.id}`]) : false;
                  return (
                    <DocumentRow
                      key={slotKey}
                      entry={{ ...entry, label: slotLabel }}
                      document={document}
                      pending={slotPending}
                      isDeleting={isDeleting}
                      onUpload={() => triggerPicker(slotType, copyNumber)}
                      onReplace={() => triggerPicker(slotType, copyNumber)}
                      onDelete={() => document && onDelete(document)}
                      hiddenInput={
                        <input
                          ref={(node) => {
                            fileInputs.current[slotKey] = node;
                          }}
                          type="file"
                          accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.tif,.tiff"
                          hidden
                          tabIndex={-1}
                          onChange={(event) => handleFile(slotType, copyNumber, event)}
                        />
                      }
                    />
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}

export default DocumentList;
