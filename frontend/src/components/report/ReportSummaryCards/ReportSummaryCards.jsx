import { FileCheck2, FileText, Percent, ShieldCheck } from 'lucide-react';

import StatusChip from '../../common/StatusChip/StatusChip';
import { getVerificationStatus } from '../../../data/statuses';
import styles from './ReportSummaryCards.module.css';

function SummaryCard({ icon: Icon, title, value, detail, children }) {
  return (
    <div className={styles.card} aria-label={title}>
      <div className={styles.cardHeader}>
        <div className={styles.iconWrap} aria-hidden="true">
          <Icon />
        </div>
        <h4 className={styles.cardTitle}>{title}</h4>
      </div>
      <div className={styles.value}>{value}</div>
      {detail && <p className={styles.detail}>{detail}</p>}
      {children}
    </div>
  );
}

function RuleCounts({ passed, failed, warnings, pending }) {
  const items = [
    { label: 'Passed', count: passed, variant: 'success' },
    { label: 'Failed', count: failed, variant: 'danger' },
    { label: 'Warning', count: warnings, variant: 'warning' },
    { label: 'Pending', count: pending, variant: 'neutral' },
  ];
  return (
    <div className={styles.breakdown}>
      {items.map(({ label, count, variant }) => (
        <StatusChip key={label} label={`${count} ${label}`} variant={variant} />
      ))}
    </div>
  );
}

/**
 * Headline summary for the validation report.
 *
 * Renders the overall verdict plus the headline aggregates from the stored
 * report and completeness data: documents checked, business-rule outcomes,
 * extracted-field totals and overall confidence.
 *
 * @param {object} props
 * @param {string|null} props.overallStatus Raw overall report status.
 * @param {object|null} props.report The stored validation report.
 * @param {object|null} props.completeness The completeness report.
 */
function ReportSummaryCards({ overallStatus, report, completeness }) {
  const overall = getVerificationStatus(overallStatus);
  const extraction = report?.extraction_summary ?? {};
  const rules = report?.rule_summary ?? {};

  return (
    <section className={styles.section} aria-label="Validation summary">
      <div className={styles.verdict}>
        <span className={styles.verdictLabel}>Overall status</span>
        <StatusChip label={overall.label} variant={overall.variant} />
      </div>
      <div className={styles.grid}>
        <SummaryCard
          icon={FileText}
          title="Documents"
          value={report?.document_summary?.length ?? 0}
          detail="Documents included in the report"
        />
        <SummaryCard
          icon={ShieldCheck}
          title="Business Rules"
          value={rules.total ?? 0}
          detail="Checks run against the application"
        >
          <RuleCounts
            passed={rules.passed ?? 0}
            failed={rules.failed ?? 0}
            warnings={rules.warnings ?? 0}
            pending={rules.pending_manual_review ?? 0}
          />
        </SummaryCard>
        <SummaryCard
          icon={FileCheck2}
          title="Fields Reviewed"
          value={extraction.total_fields ?? 0}
          detail={`${extraction.auto_verified ?? 0} verified automatically · ${extraction.pending_review ?? 0} need review`}
        />
        <SummaryCard
          icon={Percent}
          title="Field Review Progress"
          value={
            extraction.overall_confidence != null
              ? `${Math.round(extraction.overall_confidence * 100)}%`
              : '—'
          }
          detail="Across all reviewed fields"
        />
        <SummaryCard
          icon={FileCheck2}
          title="Completeness"
          value={
            completeness?.completion_percentage != null
              ? `${Math.round(completeness.completion_percentage)}%`
              : '—'
          }
          detail={`${completeness?.required_documents?.filter((item) => item.is_present).length ?? 0} of ${completeness?.required_documents?.length ?? 0} required documents`}
        />
      </div>
    </section>
  );
}

export default ReportSummaryCards;