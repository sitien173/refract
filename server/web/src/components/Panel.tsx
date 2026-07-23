import React from 'react';
import styles from '../styles/app.module.css';

interface PanelProps {
  title: string;
  supportingText?: string;
  compact?: boolean;
  headingLevel?: 'h1' | 'h2' | 'h3' | 'h4';
  children?: React.ReactNode;
  className?: string;
}

export const Panel: React.FC<PanelProps> = ({
  title,
  supportingText,
  compact = false,
  headingLevel = 'h2',
  children,
  className,
}) => {
  const HeadingTag = headingLevel;

  const panelClass = [
    styles.panelContainer,
    compact ? styles.panelCompact : '',
    className || '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <section className={panelClass}>
      <header className={styles.panelHeader}>
        <HeadingTag className={styles.panelTitle}>{title}</HeadingTag>
        {supportingText && <p className={styles.panelSupportingText}>{supportingText}</p>}
      </header>
      {children && <div className={styles.panelBody}>{children}</div>}
    </section>
  );
};
