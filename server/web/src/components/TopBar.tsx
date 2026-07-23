import React from 'react';
import styles from '../styles/app.module.css';
import { ThemeToggle } from './ThemeToggle';

interface TopBarProps {
  title?: string;
}

export const TopBar: React.FC<TopBarProps> = ({ title = 'Monitor Console' }) => {
  return (
    <header className={styles.topBar}>
      <div className={styles.topBarTitleGroup}>
        <h1 className={styles.topBarTitle}>{title}</h1>
      </div>
      <div className={styles.topBarActions}>
        <ThemeToggle />
      </div>
    </header>
  );
};
