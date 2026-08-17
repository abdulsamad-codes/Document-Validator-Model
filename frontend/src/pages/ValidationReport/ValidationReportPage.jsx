import { FileText, RefreshCw } from 'lucide-react';

import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import ReportCompleteness from '../../components/report/ReportCompleteness/ReportCompleteness';
import ReportDocuments from '../../components/report/ReportDocuments/ReportDocuments';
import ReportFields from '../../components/report/ReportFields/ReportFields';
import ReportIssues from '../../components/report/ReportIssues/ReportIssues';
import ReportRules from '../../components/report/ReportRules/ReportRules';
import ReportSummaryCards from '../../components/report/ReportSummaryCards/ReportSummaryCards';
import ReportTechnicalValidation from '../../components/report/ReportTechnicalValidation/ReportTechnicalValidation';
import ReportVisual from '../../components/report/ReportVisual/ReportVisual';
import { APPLICATION_STATUSES } from '../../data/statuses';
import { useValidationReport } from '../../hooks/useValidationReport';
import { getValidationReportHtmlUrl } from '../../services/reports';
import { formatDateTime } from '../../utils/format';
import styles from './ValidationReportPage.module.css';

function Section({ title, children, note }) {
  return (
    <section className={styles.section} aria-label={title}>
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>{title}</h3>
      </div>
      {note && <p className={styles.sectionNote}>{note}</p>}
      {children}
    </section>
  );
}

function ReportSkeleton() {
  return (
    <div aria-hidden="true">
      <div className={styles.skeletonHeader} />
      <div className={styles.skeletonGrid}>
        {Array.from({ length: 5 }, (_, index) => (
          <div className={styles.skeletonCard} key={index} />
        ))}
      </div>
      <div className={styles.skeletonTable} />
    </div>
  );
}

/**
 * Operator-facing validation report.
 *
 * Read-only aggregation of the stored pipeline results for a selected
 * application: overall verdict, per-document status, completeness, technical
 * validation, extracted/normalized fields, business-rule outcomes per
 * category, signature/stamp evidence and the issues and recommendations the
 * reviewer should address. Nothing is re-run; the printable HTML report is
 * opened from the same report data.
 */
function ValidationReportPage() {
  const {
    applications,
    appsLoading,
    appsError,
    statusFilter,
    onStatusChange,
    selectedId,
    onSelect,
    report,
    completeness,
    technical,
    analysis,
    normalized,
    loading,
    error,
    sectionErrors,
    hasAnyData,
    overallStatus,
    groupedRules,
    issues,
    recommendations,
    onRefresh,
  } = useValidationReport();

  const printableUrl = selectedId != null ? getValidationReportHtmlUrl(selectedId) : null;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Validation Report</h2>
        <p className={styles.subtitle}>
          View the complete validation result for an application — documents, checks, extracted
          fields and issues requiring attention.
        </p>
      </header>

      <div className={styles.toolbar}>
        <label className={styles.filter} htmlFor="report-app-select">
          <span className={styles.filterLabel}>Application</span>
          <select
            id="report-app-select"
            className={styles.select}
            value={selectedId ?? ''}
            onChange={(event) => onSelect(event.target.value)}
            aria-label="Select an application to report on"
            disabled={appsLoading}
          >
            <option value="">Select an application</option>
            {applications.map((app) => (
              <option key={app.id} value={app.id}>
                #{app.id} — {app.name || app.created_by} ({app.status})
              </option>
            ))}
          </select>
        </label>

        <label className={styles.filter} htmlFor="report-status-filter">
          <span className={styles.filterLabel}>Status</span>
          <select
            id="report-status-filter"
            className={styles.select}
            value={statusFilter}
            onChange={(event) => onStatusChange(event.target.value)}
            aria-label="Filter applications by status"
          >
            <option value="">All</option>
            {APPLICATION_STATUSES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <button type="button" className={styles.secondaryBtn} onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>

        {printableUrl && (
          <a
            href={printableUrl}
            target="_blank"
            rel="noreferrer"
            className={styles.secondaryBtn}
            aria-disabled={report == null}
          >
            <FileText aria-hidden="true" />
            Printable report
          </a>
        )}
      </div>

      {appsError && <ErrorState message={appsError} onRetry={onRefresh} />}

      {selectedId == null && !appsError && (
        <EmptyState
          title="Select an application"
          message="Choose an application above to load its validation report."
        />
      )}

      {selectedId != null && loading && <ReportSkeleton />}

      {selectedId != null && !loading && error && !hasAnyData && (
        <ErrorState message={error} onRetry={onRefresh} />
      )}

      {selectedId != null && !loading && !error && (
        <>
          {!hasAnyData && (
            <EmptyState
              title="No validation results yet"
              message="No validation data has been collected for this application yet."
              action={
                <button type="button" className={styles.primaryBtn} onClick={onRefresh}>
                  <RefreshCw aria-hidden="true" />
                  Refresh
                </button>
              }
            />
          )}

          {hasAnyData && (
            <>
              <Section title="Summary">
                <ReportSummaryCards
                  overallStatus={overallStatus}
                  report={report}
                  completeness={completeness}
                />
              </Section>

              {sectionErrors.report && !report && (
                <p className={styles.reportUnavailable}>{sectionErrors.report}</p>
              )}

              {report && (
                <Section title="Documents" note="Document-by-document verification status">
                  <ReportDocuments documents={report.document_summary} />
                </Section>
              )}

              {completeness && (
                <Section title="Completeness" note="Required documents and their presence">
                  <ReportCompleteness completeness={completeness} />
                </Section>
              )}

              {technical && (
                <Section title="Technical Validation" note="File quality and readability checks">
                  <ReportTechnicalValidation items={technical.items} />
                </Section>
              )}

              <Section title="Extracted & Normalized Fields">
                <ReportFields normalized={normalized} analysisItems={analysis.items} />
              </Section>

              <Section title="Business Rules" note="Results grouped by category">
                <ReportRules groups={groupedRules} />
              </Section>

              {report && (
                <Section title="Visual Evidence" note="Signature and stamp findings">
                  <ReportVisual visual={report.visual_detection_summary} />
                </Section>
              )}

              <Section title="Issues Requiring Attention">
                <ReportIssues issues={issues} recommendations={recommendations} />
              </Section>

              {report?.application && (
                <p className={styles.generatedAt}>
                  Report generated {formatDateTime(report.generated_at)} · version{' '}
                  {report.report_version}
                </p>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

export default ValidationReportPage;