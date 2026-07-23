import React from 'react';
import { useStatus, useTargets, useProfiles, useAllJobs } from '../lib/queries';
import { deriveCircuitState, formatDate } from '../lib/presentation';
import { Panel } from '../components/Panel';
import { DataTable } from '../components/DataTable';
import { StatusBadge } from '../components/StatusBadge';
import { EmptyState } from '../components/EmptyState';
import { Job } from '../lib/types';
import styles from '../styles/app.module.css';

export const Overview: React.FC = () => {
  const statusQuery = useStatus();
  const targetsQuery = useTargets();
  const profilesQuery = useProfiles();
  const allJobsResult = useAllJobs();

  const { jobs, projectsQuery, isLoading: isJobsLoading } = allJobsResult;

  const isInitialLoading =
    (statusQuery.isLoading && !statusQuery.data) ||
    (targetsQuery.isLoading && !targetsQuery.data) ||
    (profilesQuery.isLoading && !profilesQuery.data) ||
    (isJobsLoading && jobs.length === 0);

  const isInitialError =
    (statusQuery.isError && !statusQuery.data) &&
    (targetsQuery.isError && !targetsQuery.data) &&
    (profilesQuery.isError && !profilesQuery.data) &&
    (allJobsResult.isError && jobs.length === 0);

  const hasRefetchError =
    (statusQuery.isError && Boolean(statusQuery.data)) ||
    (targetsQuery.isError && Boolean(targetsQuery.data)) ||
    (profilesQuery.isError && Boolean(profilesQuery.data)) ||
    (allJobsResult.isError && jobs.length > 0) ||
    Boolean(allJobsResult.errors && allJobsResult.errors.length > 0);

  if (isInitialLoading) {
    return (
      <div role="status" aria-live="polite" className={styles.placeholderPanel}>
        <p className="ff-text-md ff-fg-subdued">Loading Overview data...</p>
      </div>
    );
  }

  if (isInitialError) {
    return (
      <div role="alert" aria-live="polite" className={styles.placeholderPanel}>
        <p className="ff-text-md ff-fg-red">Failed to load Overview data.</p>
      </div>
    );
  }

  const statusData = statusQuery.data;
  const targetsData = targetsQuery.data ?? [];
  const profilesData = profilesQuery.data;
  const projectsData = projectsQuery.data ?? [];

  const recentJobs = jobs.slice(0, 5);

  const totalTargets = targetsData.length;
  const healthyTargets = targetsData.filter((t) => t.healthy).length;
  const degradedTargets = targetsData.filter((t) => !t.healthy).length;
  const openCircuitTargets = targetsData.filter(
    (t) => deriveCircuitState(t.circuit_open_until) === 'circuit-open'
  ).length;

  const totalProjects = projectsData.length;
  const cleanProjects = projectsData.filter((p) => p.clean).length;
  const dirtyProjects = projectsData.filter((p) => !p.clean).length;

  const jobColumns = [
    { key: 'id', header: 'Job ID', render: (j: Job) => j.id },
    { key: 'workflow', header: 'Workflow', render: (j: Job) => j.workflow },
    { key: 'profile', header: 'Profile', render: (j: Job) => j.profile },
    { key: 'state', header: 'State', render: (j: Job) => <StatusBadge state={j.state} /> },
    { key: 'created_at', header: 'Created', render: (j: Job) => formatDate(j.created_at) },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      {hasRefetchError && (
        <div
          role="status"
          aria-live="polite"
          style={{
            backgroundColor: 'var(--color-decorative-yellow)',
            color: 'var(--color-icon-yellow)',
            padding: 'var(--space-xs) var(--space-md)',
            borderRadius: 'var(--radius-xs)',
            fontSize: 'var(--type-text-xs-size)',
            fontWeight: 600,
          }}
        >
          Could not refresh. Showing last known data.
        </div>
      )}

      {/* Area 1: System Status */}
      <Panel title="System Status" headingLevel="h2">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 'var(--space-md)' }}>
          <div className={styles.metricChip} style={{ flexDirection: 'column', alignItems: 'flex-start', padding: 'var(--space-sm)' }}>
            <span className={styles.metricLabel}>Workers</span>
            <span className={styles.metricValue} style={{ fontSize: 'var(--type-text-xl-size)' }}>
              {statusData?.workers ?? 0}
            </span>
          </div>
          <div className={styles.metricChip} style={{ flexDirection: 'column', alignItems: 'flex-start', padding: 'var(--space-sm)' }}>
            <span className={styles.metricLabel}>Active Jobs</span>
            <span className={styles.metricValue} style={{ fontSize: 'var(--type-text-xl-size)' }}>
              {statusData?.active_jobs ?? 0}
            </span>
          </div>
          <div className={styles.metricChip} style={{ flexDirection: 'column', alignItems: 'flex-start', padding: 'var(--space-sm)' }}>
            <span className={styles.metricLabel}>Queued Jobs</span>
            <span className={styles.metricValue} style={{ fontSize: 'var(--type-text-xl-size)' }}>
              {statusData?.queued_jobs ?? 0}
            </span>
          </div>
        </div>
      </Panel>

      {/* Area 2: Recent Jobs */}
      <Panel title="Recent Jobs" supportingText="Latest 5 jobs across all projects" headingLevel="h2">
        {recentJobs.length === 0 ? (
          <EmptyState message="No recent jobs found." />
        ) : (
          <DataTable
            caption="Recent Jobs Table"
            columns={jobColumns}
            rows={recentJobs}
            getRowKey={(j) => j.id}
          />
        )}
      </Panel>

      {/* Summary Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-md)' }}>
        {/* Area 3: Target Health */}
        <Panel title="Target Health" headingLevel="h3">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className={styles.metricLabel}>Total Targets</span>
              <span className={styles.metricValue}>{totalTargets}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className={styles.metricLabel}>Healthy</span>
              <span className={styles.metricValue} style={{ color: 'var(--color-text-code-green)' }}>{healthyTargets}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className={styles.metricLabel}>Degraded</span>
              <span className={styles.metricValue} style={{ color: 'var(--color-icon-yellow)' }}>{degradedTargets}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className={styles.metricLabel}>Open Circuits</span>
              <span className={styles.metricValue} style={{ color: 'var(--color-icon-yellow)' }}>{openCircuitTargets}</span>
            </div>
          </div>
        </Panel>

        {/* Area 4: Projects Summary */}
        <Panel title="Projects Summary" headingLevel="h3">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className={styles.metricLabel}>Total Projects</span>
              <span className={styles.metricValue}>{totalProjects}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className={styles.metricLabel}>Clean</span>
              <span className={styles.metricValue} style={{ color: 'var(--color-text-code-green)' }}>{cleanProjects}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className={styles.metricLabel}>Dirty</span>
              <span className={styles.metricValue} style={{ color: 'var(--color-icon-yellow)' }}>{dirtyProjects}</span>
            </div>
          </div>
        </Panel>

        {/* Area 5: Profiles Summary */}
        <Panel title="Profiles Summary" headingLevel="h3">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className={styles.metricLabel}>Default Profile</span>
              <span className={styles.metricValue}>{profilesData?.default || 'None'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className={styles.metricLabel}>Available Profiles</span>
              <span className={styles.metricValue}>{profilesData?.available.length ?? 0}</span>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
};
