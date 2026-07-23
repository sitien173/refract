import React from 'react';
import styles from '../styles/app.module.css';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

interface AppShellProps {
  children?: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  return (
    <div className={styles.appLayout}>
      <Sidebar />
      <div className={styles.mainContainer}>
        <TopBar />
        <main className={styles.contentArea}>
          {children || (
            <div className={styles.placeholderCard}>
              <h2>Monitor Console</h2>
              <p style={{ marginTop: '8px', color: 'var(--color-text-subdued)' }}>
                Phase 1 Flowforge application shell ready.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
