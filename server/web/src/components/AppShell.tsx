import React from 'react';
import { useLocation } from 'react-router-dom';
import styles from '../styles/app.module.css';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

interface AppShellProps {
  children?: React.ReactNode;
}

function getTitleFromPath(pathname: string): string {
  switch (pathname) {
    case '/projects':
      return 'Projects';
    case '/targets':
      return 'Targets';
    case '/profiles':
      return 'Profiles';
    case '/':
    default:
      return 'Overview';
  }
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const location = useLocation();
  const title = getTitleFromPath(location.pathname);

  return (
    <div className={styles.appLayout}>
      <Sidebar />
      <div className={styles.mainContainer}>
        <TopBar title={title} />
        <main className={styles.contentArea}>{children}</main>
      </div>
    </div>
  );
};
