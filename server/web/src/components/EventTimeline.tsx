import React from 'react';
import { useJobEvents } from '../lib/queries';
import styles from '../styles/app.module.css';

interface EventTimelineProps {
  jobId: string;
}

export const EventTimeline: React.FC<EventTimelineProps> = ({ jobId }) => {
  const { data, isLoading, isError } = useJobEvents(jobId, { enabled: Boolean(jobId) });

  if (isLoading && data === undefined) {
    return (
      <div className={styles.timelineSection}>
        <h3 className={styles.timelineTitle}>Event Timeline</h3>
        <p role="status">Loading events...</p>
      </div>
    );
  }

  if (isError && data === undefined) {
    return (
      <div className={styles.timelineSection}>
        <h3 className={styles.timelineTitle}>Event Timeline</h3>
        <p role="alert">Failed to load events.</p>
      </div>
    );
  }

  return (
    <div className={styles.timelineSection}>
      <h3 className={styles.timelineTitle}>Event Timeline</h3>
      {isError && (
        <div className={styles.warningBanner}>
          Could not refresh. Showing last known data.
        </div>
      )}
      {data && data.length === 0 ? (
        <p>No events recorded.</p>
      ) : (
        <ol className={styles.timelineList}>
          {data?.map((event) => (
            <li key={event.id} className={styles.timelineItem}>
              <div className={styles.timelineHeader}>
                <span className={styles.eventKind}>{event.kind}</span>
                <time dateTime={event.created_at}>{event.created_at}</time>
              </div>
              <pre className={styles.eventData}>{JSON.stringify(event.data, null, 2)}</pre>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
};
