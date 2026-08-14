import StatusChip from '../../common/StatusChip/StatusChip';
import { getRuleResultStatus } from '../../../data/statuses';
import { getDocumentTypeConfig } from '../../../data/documents';
import styles from './ReportCompleteness.module.css';

function NoticeList({ title, items, tone }) {
  if (!items || items.length === 0) {
    return null;
  }
  return (
    <div className={`${styles.notice} ${styles[tone] ?? ''}`}>
      <h4 className={styles.noticeTitle}>{title}</h4>
      <ul className={styles.noticeList}>
        {items.map((item) => {
          const label =
            typeof item === 'string'
              ? getDocumentTypeConfig(item).label
              : `${getDocumentTypeConfig(item.document_type).label} (${item.copy_count} copies)`;
          return <li key={typeof item === 'string' ? item : item.document_type}>{label}</li>;
        })}
      </ul>
    </div>
  );
}

/**
 * Completeness result section.
 *
 * Shows the completeness verdict and completion percentage, the presence of
 * every required document type, and any missing, duplicate or unexpected
 * documents the backend reported.
 *
 * @param {object} props
 * @param {object|null} props.completeness The completeness report.
 */
function ReportCompleteness({ completeness }) {
  if (!completeness) {
    return null;
  }
  const status = getRuleResultStatus(completeness.status);

  return (
    <div>
      <div className={styles.heading}>
        <div className={styles.headingMeta}>
          <StatusChip label={status.label} variant={status.variant} />
          <span className={styles.percentage}>
            {Math.round(completeness.completion_percentage)}% complete
          </span>
        </div>
        <p className={styles.detail}>
          {completeness.required_documents?.filter((item) => item.is_present).length ?? 0} of{' '}
          {completeness.required_documents?.length ?? 0} required documents uploaded
        </p>
      </div>

      <ul className={styles.requiredList}>
        {(completeness.required_documents ?? []).map((item) => {
          const config = getDocumentTypeConfig(item.document_type);
          return (
            <li key={item.document_type} className={styles.requiredRow}>
              <span className={styles.requiredLabel}>{config.label}</span>
              <StatusChip
                label={item.is_present ? 'Present' : 'Missing'}
                variant={item.is_present ? 'success' : 'danger'}
              />
              <span className={styles.copyCount}>
                {item.copy_count} {item.copy_count === 1 ? 'copy' : 'copies'}
              </span>
            </li>
          );
        })}
      </ul>

      <NoticeList title="Missing documents" items={completeness.missing_documents ?? []} tone="danger" />
      <NoticeList
        title="Duplicate documents"
        items={completeness.duplicate_documents ?? []}
        tone="warning"
      />
      <NoticeList
        title="Unexpected documents"
        items={completeness.unexpected_documents ?? []}
        tone="neutral"
      />
    </div>
  );
}

export default ReportCompleteness;