import React from 'react';
import { NavLink, Link } from 'react-router-dom';
import styles from '../styles/app.module.css';
import activitySvg from '../assets/icons/activity.svg';
import folderSvg from '../assets/icons/folder.svg';
import layersSvg from '../assets/icons/layers.svg';
import cpuSvg from '../assets/icons/cpu.svg';
import slidersSvg from '../assets/icons/sliders.svg';

interface NavItemDef {
  id: string;
  label: string;
  path: string;
  icon: string;
  disabled?: boolean;
}

const navItems: NavItemDef[] = [
  { id: 'overview', label: 'Overview', path: '/', icon: activitySvg },
  { id: 'projects', label: 'Projects', path: '/projects', icon: folderSvg },
  { id: 'jobs', label: 'Jobs - Unavailable', path: '/jobs', icon: layersSvg, disabled: true },
  { id: 'targets', label: 'Targets', path: '/targets', icon: cpuSvg },
  { id: 'profiles', label: 'Profiles', path: '/profiles', icon: slidersSvg },
];

export const Sidebar: React.FC = () => {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.sidebarHeader}>
        <Link to="/" className={styles.brand}>
          <span>OpenMCP</span>
          <span className={styles.brandBadge}>Console</span>
        </Link>
      </div>
      <nav className={styles.navSection} aria-label="Main Navigation">
        <ul className={styles.navList}>
          {navItems.map((item) => {
            if (item.disabled) {
              return (
                <li
                  key={item.id}
                  className={styles.navItemDisabled}
                  aria-disabled="true"
                >
                  <span
                    className={styles.navIcon}
                    style={
                      {
                        '--icon-url': `url(${item.icon})`,
                        maskImage: `url(${item.icon})`,
                        WebkitMaskImage: `url(${item.icon})`,
                      } as React.CSSProperties
                    }
                    aria-hidden="true"
                    data-testid={`nav-icon-${item.id}`}
                  />
                  <span>{item.label}</span>
                </li>
              );
            }

            return (
              <li key={item.id}>
                <NavLink
                  to={item.path}
                  end={item.path === '/'}
                  className={({ isActive }) =>
                    isActive
                      ? `${styles.navItem} ${styles.navItemActive}`
                      : styles.navItem
                  }
                >
                  <span
                    className={styles.navIcon}
                    style={
                      {
                        '--icon-url': `url(${item.icon})`,
                        maskImage: `url(${item.icon})`,
                        WebkitMaskImage: `url(${item.icon})`,
                      } as React.CSSProperties
                    }
                    aria-hidden="true"
                    data-testid={`nav-icon-${item.id}`}
                  />
                  <span>{item.label}</span>
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className={styles.sidebarFooter}>
        <span>OpenMCP v0.1.0</span>
      </div>
    </aside>
  );
};
