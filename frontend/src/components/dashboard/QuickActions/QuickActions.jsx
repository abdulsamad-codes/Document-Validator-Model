import { FolderOpen, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import styles from './QuickActions.module.css';

const ACTIONS = [
  {
    id: 'new-application',
    label: 'New Application',
    description: 'Start a new document verification case.',
    to: '/applications/new',
    icon: Plus,
  },
  {
    id: 'view-applications',
    label: 'View Applications',
    description: 'Browse and manage existing applications.',
    to: '/applications',
    icon: FolderOpen,
  },
];

/**
 * Quick Actions dashboard section.
 *
 * Two shortcut cards that navigate to the application creation and list
 * routes. Icons are decorative; navigation is handled by React Router links.
 */
function QuickActions() {
  return (
    <section className={styles.section} aria-label="Quick actions">
      <h3 className={styles.title}>Quick Actions</h3>
      <div className={styles.grid}>
        {ACTIONS.map(({ id, label, description, to, icon: Icon }) => (
          <Link key={id} to={to} className={styles.action}>
            <div className={styles.iconWrap} aria-hidden="true">
              <Icon />
            </div>
            <div className={styles.meta}>
              <span className={styles.actionLabel}>{label}</span>
              <span className={styles.actionDescription}>{description}</span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

export default QuickActions;
