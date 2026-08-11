import { Bell, Menu, Search } from 'lucide-react';

import { useAuth } from '../../../hooks/useAuth';
import { USER_PROFILE } from '../../../data/dashboard';
import ThemeToggle from '../../theme/ThemeToggle/ThemeToggle';
import styles from './Navbar.module.css';

/**
 * Top navigation bar of the dashboard.
 *
 * Left side holds the responsive menu toggle, the page title and a breadcrumb;
 * the right side holds the search box, notifications, a functional theme toggle
 * and the employee profile with the current date.
 *
 * @param {string} title Page title shown in the bar.
 * @param {string} breadcrumb Breadcrumb trail for the current page.
 * @param {boolean} showMenu Whether the hamburger toggle is visible.
 * @param {Function} onToggleSidebar Callback fired when the toggle is clicked.
 */
function Navbar({ title, breadcrumb, showMenu = false, onToggleSidebar }) {
  const { user } = useAuth();
  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

  const displayName = user?.name ?? USER_PROFILE.name;
  const initials =
    user?.initials ??
    displayName
      .split(' ')
      .map((part) => part[0])
      .filter(Boolean)
      .slice(0, 2)
      .join('')
      .toUpperCase();

  return (
    <header className={styles.navbar}>
      <div className={styles.left}>
        {showMenu && (
          <button
            className={styles.iconButton}
            type="button"
            aria-label="Toggle navigation"
            onClick={onToggleSidebar}
          >
            <Menu aria-hidden="true" />
          </button>
        )}
        <div className={styles.titles}>
          <h1 className={styles.title}>{title}</h1>
          <span className={styles.breadcrumb}>{breadcrumb}</span>
        </div>
      </div>

      <div className={styles.right}>
        <label className={styles.search}>
          <Search className={styles.searchIcon} aria-hidden="true" />
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search..."
            aria-label="Search"
          />
        </label>

        <button className={styles.iconButton} type="button" aria-label="Notifications">
          <Bell aria-hidden="true" />
          <span className={styles.notificationDot} aria-hidden="true" />
        </button>

        <ThemeToggle />

        <div className={styles.profile}>
          <div className={styles.avatar} aria-hidden="true">
            {initials}
          </div>
          <div className={styles.profileInfo}>
            <span className={styles.profileName}>{displayName}</span>
            <span className={styles.date}>{today}</span>
          </div>
        </div>
      </div>
    </header>
  );
}

export default Navbar;
