import React from 'react';
import { NavLink } from 'react-router-dom';
import styles from '../styles/app.module.css';
import activitySvg from '../assets/icons/activity.svg';
import folderSvg from '../assets/icons/folder.svg';
import layersSvg from '../assets/icons/layers.svg';
import cpuSvg from '../assets/icons/cpu.svg';
import slidersSvg from '../assets/icons/sliders.svg';

interface NavItemDef {
  path: string;
  label: string;
  icon: string;
}

const navItems: NavItemDef[] = [
  { path: '/', label: 'Overview', icon: activitySvg },
  { path: '/projects', label: 'Projects', icon: folderSvg },
  { path: '/jobs', label: 'Jobs', icon: layersSvg },
  { path: '/targets', label: 'Targets', icon: cpuSvg },
  { path: '/profiles', label: 'Profiles', icon: slidersSvg },
];

export const Sidebar: React.FC = () => {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.sidebarHeader}>
        <a href="/" className={styles.brand}>
          <span>OpenMCP</span>
          <span className={styles.brandBadge}>Console</span>
        </a>
      </div>
      <nav className={styles.navSection}>
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              isActive ? `${styles.navItem} ${styles.navItemActive}` : styles.navItem
            }
            end={item.path === '/'}
          >
            <span className={styles.navIcon}>
              <img src={item.icon} alt="" width={16} height={16} />
            </span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className={styles.sidebarFooter}>
        <span>OpenMCP v0.1.0</span>
      </div>
    </aside>
  );
};
