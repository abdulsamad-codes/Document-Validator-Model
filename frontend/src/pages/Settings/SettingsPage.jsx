import { Link } from 'react-router-dom';
import {
  ArrowRight,
  KeyRound,
  LogOut,
  MessageSquare,
  RefreshCw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  User as UserIcon,
} from 'lucide-react';

import { ADMIN_NAV_ITEMS } from '../../data/navigation';
import { useAuth } from '../../hooks/useAuth';
import { humanizeEnum } from '../../utils/format';
import styles from './SettingsPage.module.css';

/**
 * Humanize a backend role value into an employee-facing label.
 */
function roleLabel(role) {
  switch (String(role ?? '').toLowerCase()) {
    case 'admin':
      return 'Administrator';
    case 'reviewer':
      return 'Reviewer';
    case 'operator':
      return 'Operator';
    case 'employee':
      return 'Employee';
    default:
      return role ? humanizeEnum(role) : '—';
  }
}

/**
 * Settings page.
 *
 * Shows the signed-in user's profile and account information from the
 * authenticated session plus a functional sign-out. Password/security and
 * preference controls are intentionally not fabricated: no backend endpoint
 * supports them, so those sections are marked as unavailable. The
 * Administration section carries the internal Feedback and Continuous
 * Learning tools, which are privileged functions not shown in the main
 * sidebar.
 */
function SettingsPage() {
  const { user, loading, logout } = useAuth();

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

      {loading ? (
        <p className={styles.loading}>Loading your profile…</p>
      ) : (
        <>
          <section className={styles.card} aria-label="Profile information">
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon} aria-hidden="true">
                <UserIcon />
              </span>
              <div className={styles.cardTitleWrap}>
                <h3 className={styles.cardTitle}>Profile</h3>
                <p className={styles.cardDescription}>
                  Your employee profile as recorded for this workspace.
                </p>
              </div>
            </div>
            <dl className={styles.details}>
              <div className={styles.detailRow}>
                <dt>Name</dt>
                <dd>{user?.name ?? '—'}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Email</dt>
                <dd>{user?.email ?? '—'}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Employee ID</dt>
                <dd>{user?.employee_id ?? '—'}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Role</dt>
                <dd>{roleLabel(user?.role)}</dd>
              </div>
            </dl>
          </section>

          <section className={styles.card} aria-label="Account">
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon} aria-hidden="true">
                <Settings2 />
              </span>
              <div className={styles.cardTitleWrap}>
                <h3 className={styles.cardTitle}>Account</h3>
                <p className={styles.cardDescription}>
                  {user ? `Signed in as ${user.email ?? user.employee_id ?? 'you'}.` : 'You are not signed in.'}
                </p>
              </div>
            </div>
            <div className={styles.cardBody}>
              <p className={styles.bodyHint}>
                Signing out ends your current session on this device.
              </p>
              <button type="button" className={styles.signOutBtn} onClick={logout}>
                <LogOut aria-hidden="true" />
                Sign out
              </button>
            </div>
          </section>

          <section className={styles.card} aria-label="Security">
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon} aria-hidden="true">
                <KeyRound />
              </span>
              <div className={styles.cardTitleWrap}>
                <h3 className={styles.cardTitle}>Password & Security</h3>
                <p className={styles.cardDescription}>
                  Manage how you access your account.
                </p>
              </div>
            </div>
            <div className={styles.cardBody}>
              <p className={styles.unavailable}>
                Changing your password is not available from this application. Contact your
                administrator for password or account security requests.
              </p>
            </div>
          </section>

          <section className={styles.card} aria-label="Preferences">
            <div className={styles.cardHeader}>
              <span className={styles.cardIcon} aria-hidden="true">
                <SlidersHorizontal />
              </span>
              <div className={styles.cardTitleWrap}>
                <h3 className={styles.cardTitle}>Preferences</h3>
                <p className={styles.cardDescription}>
                  Personalise how this workspace looks and behaves.
                </p>
              </div>
            </div>
            <div className={styles.cardBody}>
              <p className={styles.unavailable}>
                No preferences are configurable from this application at this time.
              </p>
            </div>
          </section>
        </>
      )}

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