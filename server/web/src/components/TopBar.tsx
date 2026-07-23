import React, { useRef } from 'react';
import styles from '../styles/app.module.css';
import { ThemeToggle } from './ThemeToggle';
import { useStatus } from '../lib/queries';
import { DaemonStatus } from '../lib/types';
import circleCheckSvg from '../assets/icons/circle-check.svg';
import triangleAlertSvg from '../assets/icons/triangle-alert.svg';
import wifiOffSvg from '../assets/icons/wifi-off.svg';

interface TopBarProps {
  title?: string;
}

export const TopBar: React.FC<TopBarProps> = ({ title = 'Monitor Console' }) => {
  const statusQuery = useStatus();
  const data = statusQuery?.data;
  const isError = Boolean(statusQuery?.isError);
  const dataUpdatedAt = statusQuery?.dataUpdatedAt || 0;

  const lastKnownDataRef = useRef<DaemonStatus | undefined>(undefined);
  const lastKnownUpdatedAtRef = useRef<number | undefined>(undefined);

  if (data) {
    lastKnownDataRef.current = data;
  }
  if (dataUpdatedAt > 0) {
    lastKnownUpdatedAtRef.current = dataUpdatedAt;
  }

  let connectionState: 'Connecting' | 'Running' | 'Degraded' | 'Disconnected';
  let iconUrl: string;
  let pillModifierClass = styles.statusConnecting;

  if (isError) {
    connectionState = 'Disconnected';
    iconUrl = wifiOffSvg;
    pillModifierClass = styles.statusDisconnected;
  } else if (data) {
    if (data.status === 'running') {
      connectionState = 'Running';
      iconUrl = circleCheckSvg;
      pillModifierClass = styles.statusRunning;
    } else {
      connectionState = 'Degraded';
      iconUrl = triangleAlertSvg;
      pillModifierClass = styles.statusDegraded;
    }
  } else {
    connectionState = 'Connecting';
    iconUrl = triangleAlertSvg;
    pillModifierClass = styles.statusConnecting;
  }

  const activeData = data || lastKnownDataRef.current;
  const activeUpdatedAt = data ? dataUpdatedAt : lastKnownUpdatedAtRef.current;

  const workersCount = activeData ? activeData.workers.toString() : '—';
  const activeJobsCount = activeData ? activeData.active_jobs.toString() : '—';
  const queuedJobsCount = activeData ? activeData.queued_jobs.toString() : '—';

  const lastUpdatedStr = activeUpdatedAt
    ? new Date(activeUpdatedAt).toLocaleTimeString()
    : '—';

  return (
    <header className={styles.topBar}>
      <div className={styles.topBarTitleGroup}>
        <h1 className={styles.topBarTitle}>{title}</h1>
      </div>
      <div className={styles.topBarMetrics}>
        <div
          className={`${styles.statusPill} ${pillModifierClass}`}
          data-testid="status-pill"
        >
          <span
            className={styles.statusIcon}
            style={
              {
                maskImage: `url(${iconUrl})`,
                WebkitMaskImage: `url(${iconUrl})`,
              } as React.CSSProperties
            }
            aria-hidden="true"
          />
          <span>{connectionState}</span>
        </div>
        <div className={styles.metricChip}>
          <span className={styles.metricLabel}>Workers:</span>
          <span className={styles.metricValue} data-testid="count-workers">
            {workersCount}
          </span>
        </div>
        <div className={styles.metricChip}>
          <span className={styles.metricLabel}>Active:</span>
          <span className={styles.metricValue} data-testid="count-active">
            {activeJobsCount}
          </span>
        </div>
        <div className={styles.metricChip}>
          <span className={styles.metricLabel}>Queued:</span>
          <span className={styles.metricValue} data-testid="count-queued">
            {queuedJobsCount}
          </span>
        </div>
        <div className={styles.metricChip}>
          <span className={styles.metricLabel}>Updated:</span>
          <span className={styles.metricValue} data-testid="last-updated">
            {lastUpdatedStr}
          </span>
        </div>
      </div>
      <div className={styles.topBarActions}>
        <ThemeToggle />
      </div>
    </header>
  );
};
