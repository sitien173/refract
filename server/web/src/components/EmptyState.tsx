import React from 'react';
import styles from '../styles/app.module.css';

interface EmptyStateProps {
  message: string;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ message, className }) => {
  return (
    <div className={`${styles.emptyStateContainer} ${className || ''}`.trim()}>
      <p className={styles.emptyStateMessage}>{message}</p>
    </div>
  );
};
