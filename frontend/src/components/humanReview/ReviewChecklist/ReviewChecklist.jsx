import { CheckCircle2 } from 'lucide-react';

import styles from './ReviewChecklist.module.css';

/**
 * Manual verification checklist.
 *
 * Renders every checklist item with its state. All items must be checked to
 * approve an application; the backend enforces the same rule on submission.
 *
 * @param {object} props
 * @param {object[]} props.items Checklist items from the review screen.
 * @param {object} props.checked Map of item name to boolean.
 * @param {Function} props.onToggle Toggle handler (item name).
 * @param {boolean} props.readOnly Disable toggling.
 */
function ReviewChecklist({ items, checked, onToggle, readOnly = false }) {
  const total = items?.length ?? 0;
  const checkedCount = items?.filter((item) => checked[item.item_name]).length ?? 0;

  if (total === 0) {
    return (
      <p className={styles.empty}>No checklist items are defined for this review.</p>
    );
  }

  return (
    <div>
      <div className={styles.heading}>
        <span className={styles.count}>
          <CheckCircle2 className={styles.countIcon} aria-hidden="true" />
          {checkedCount} of {total} checked
        </span>
        <span className={styles.hint}>All items are required to approve.</span>
      </div>
      <ul className={styles.list}>
        {items.map((item) => (
          <li key={item.item_name} className={styles.row}>
            <label className={styles.label}>
              <input
                type="checkbox"
                className={styles.checkbox}
                checked={Boolean(checked[item.item_name])}
                disabled={readOnly}
                onChange={() => onToggle(item.item_name)}
              />
              <span className={styles.itemName}>{item.item_name}</span>
            </label>
            {item.reviewer && item.checked_at && (
              <span className={styles.reviewedBy}>
                by {item.reviewer}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default ReviewChecklist;