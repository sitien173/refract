import React from 'react';
import styles from '../styles/app.module.css';
import activitySvg from '../assets/icons/activity.svg';
import folderSvg from '../assets/icons/folder.svg';
import layersSvg from '../assets/icons/layers.svg';
import cpuSvg from '../assets/icons/cpu.svg';
import slidersSvg from '../assets/icons/sliders.svg';

interface NavItemDef {
  id: string;
  label: string;
  icon: string;
}

const navItems: NavItemDef[] = [
  { id: 'overview', label: 'Overview', icon: activitySvg },
  { id: 'projects', label: 'Projects', icon: folderSvg },
  { id: 'jobs', label: 'Jobs', icon: layersSvg },
  { id: 'targets', label: 'Targets', icon: cpuSvg },
  { id: 'profiles', label: 'Profiles', icon: slidersSvg },
];

export const Sidebar: React.FC = () => {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.sidebarHeader}>
        <a href="/dashboard" className={styles.brand}>
          <span>OpenMCP</span>
          <span className={styles.brandBadge}>Console</span>
        </a>
      </div>
      <nav className={styles.navSection} aria-label="Main Navigation">
        {navItems.map((item) => {
          const isSelected = item.id === 'overview';
          return (
            <button
              key={item.id}
              type="button"
              className={
                isSelected
                  ? `${styles.navItem} ${styles.navItemActive}`
                  : styles.navItem
              }
              aria-current={isSelected ? 'page' : undefined}
            >
              <span className={styles.navIcon}>
                <img src={item.icon} alt="" width={16} height={16} />
              </span>
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      <div className={styles.sidebarFooter}>
        <span>OpenMCP v0.1.0</span>
      </div>
    </aside>
  );
};
