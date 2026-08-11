import { Link } from 'react-router-dom';
import { ArrowRight, MessageSquare, RefreshCw, ShieldCheck } from 'lucide-react';

import { ADMIN_NAV_ITEMS } from '../../data/navigation';
import styles from './SettingsPage.module.css';

/**
 * Settings page.
 *
 * Surface-level settings are intentionally minimal for now. The Administration
 * section carries the internal Feedback and Continuous Learning tools, which
 * are privileged functions not shown in the main sidebar. Each entry is marked
 * as restricted so the section reads as admin-only without fabricating a
 * permissions gate.
 */
function SettingsPage() {
  const administrationItems = ADMIN_NAV_ITEMS.map((item) => {
    const iconByType = {
      feedback: MessageSquare,
      'continuous-learning': RefreshCw,
    };
    const Icon = iconByType[item.id] ?? MessageSquare;
    return { ...item, Icon };
  });

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Settings</h2>
        <p className={styles.subtitle}>
          Manage your workspace preferences and administrative tools.
        </p>
      </header>

      <section className={styles.card} aria-label="Administration settings">
        <div className={styles.cardHeader}>
          <span className={styles.cardIcon} aria-hidden="true">
            <ShieldCheck />
          </span>
          <div className={styles.cardTitleWrap}>
            <h3 className={styles.cardTitle}>Administration</h3>
            <p className={styles.cardDescription}>
              Internal system and AI dataset management. Restricted to
              administrators.
            </p>
          </div>
          <span className={styles.restricted}>Restricted</span>
        </div>

        <ul className={styles.adminList}>
          {administrationItems.map(({ id, label, path, Icon }) => (
            <li key={id}>
              <Link to={path} className={styles.adminLink}>
                <span className={styles.adminIcon} aria-hidden="true">
                  <Icon />
                </span>
                <span className={styles.adminMeta}>
                  <span className={styles.adminLabel}>{label}</span>
                  <span className={styles.adminHint}>
                    {id === 'feedback'
                      ? 'Review correction history and export analytics.'
                      : 'Manage dataset versions, generation and exports.'}
                  </span>
                </span>
                <ArrowRight className={styles.adminArrow} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default SettingsPage;
