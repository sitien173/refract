import React from 'react';
import { useJob } from '../lib/queries';
import { StatusBadge } from './StatusBadge';
import { EventTimeline } from './EventTimeline';
import styles from '../styles/app.module.css';

export interface InspectorProps {
  jobId: string;
  onClose: () => void;
}

export const Inspector: React.FC<InspectorProps> = ({ jobId, onClose }) => {
  const { data, isLoading, isError } = useJob(jobId, { enabled: Boolean(jobId) });

  return (
    <aside className={styles.inspector} aria-labelledby="inspector-heading">
      <div className={styles.inspectorHeader}>
        <h2 id="inspector-heading" className={styles.inspectorTitle}>
          Job Details
        </h2>
        <button
          type="button"
          className={styles.inspectorCloseBtn}
          onClick={onClose}
          aria-label="Close job details"
        >
          Close
        </button>
      </div>

      {isLoading && data === undefined && (
        <p role="status">Loading job details...</p>
      )}

      {isError && data === undefined && (
        <p role="alert">Failed to load job details.</p>
      )}

      {isError && data !== undefined && (
        <div className={styles.warningBanner}>
          Could not refresh. Showing last known data.
        </div>
      )}

      {data !== undefined && (
        <div className={styles.inspectorSection}>
          <div className={styles.inspectorRow}>
            <span className={styles.inspectorLabel}>Job ID</span>
            <span className={styles.inspectorValue}>{data.id}</span>
          </div>
          <div className={styles.inspectorRow}>
            <span className={styles.inspectorLabel}>Workflow</span>
            <span className={styles.inspectorValue}>{data.workflow}</span>
          </div>
          <div className={styles.inspectorRow}>
            <span className={styles.inspectorLabel}>Profile</span>
            <span className={styles.inspectorValue}>{data.profile}</span>
          </div>
          <div className={styles.inspectorRow}>
            <span className={styles.inspectorLabel}>Project ID</span>
            <span className={styles.inspectorValue}>{data.project_id}</span>
          </div>
          <div className={styles.inspectorRow}>
            <span className={styles.inspectorLabel}>Attempts</span>
            <span className={styles.inspectorValue}>{data.attempts}</span>
          </div>
          <div className={styles.inspectorRow}>
            <span className={styles.inspectorLabel}>Created At</span>
            <time dateTime={data.created_at}>{data.created_at}</time>
          </div>
          <div className={styles.inspectorRow}>
            <span className={styles.inspectorLabel}>Updated At</span>
            <time dateTime={data.updated_at}>{data.updated_at}</time>
          </div>
          <div className={styles.inspectorRow}>
            <span className={styles.inspectorLabel}>State</span>
            <StatusBadge state={data.state} />
          </div>
        </div>
      )}

      <EventTimeline jobId={jobId} />
    </aside>
  );
};
