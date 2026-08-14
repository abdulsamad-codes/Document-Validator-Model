import StatusChip from '../../common/StatusChip/StatusChip';
import { getRuleResultStatus } from '../../../data/statuses';
import styles from './ReportRules.module.css';

function CategoryCount({ count, label, variant }) {
  return (
    <StatusChip label={`${count} ${label}`} variant={variant} />
  );
}

/**
 * Business-rule results grouped by category.
 *
 * Every category shows its Passed / Failed / Warning / Pending totals plus the
 * individual rule outcomes and their messages.
 *
 * @param {object} props
 * @param {object[]} props.groups Per-category rule groups with totals and items.
 */
function ReportRules({ groups }) {
  if (!groups || groups.length === 0) {
    return (
      <p className={styles.empty}>
        No business-rule results are available for this application.
      </p>
    );
  }

  return (
    <div className={styles.groups}>
      {groups.map((group) => (
        <section key={group.label} className={styles.group} aria-label={group.label}>
          <div className={styles.groupHeader}>
            <h4 className={styles.groupTitle}>{group.label}</h4>
            <div className={styles.groupCounts}>
              <CategoryCount count={group.passed} label="Passed" variant="success" />
              <CategoryCount count={group.failed} label="Failed" variant="danger" />
              <CategoryCount count={group.warnings} label="Warning" variant="warning" />
              <CategoryCount count={group.pending} label="Pending" variant="neutral" />
            </div>
          </div>

          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Check</th>
                <th scope="col">Result</th>
                <th scope="col">Detail</th>
              </tr>
            </thead>
            <tbody>
              {group.items.map((rule) => {
                const status = getRuleResultStatus(rule.status);
                return (
                  <tr key={rule.rule_id ?? rule.rule_name}>
                    <td data-label="Check" className={styles.ruleCell}>
                      {rule.rule_name}
                    </td>
                    <td data-label="Result">
                      <StatusChip label={status.label} variant={status.variant} />
                    </td>
                    <td data-label="Detail" className={styles.messageCell}>
                      {rule.message || '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}

export default ReportRules;