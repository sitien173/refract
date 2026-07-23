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

  const { jobs, projectsQuery } = allJobsResult;

  const hasRefetchError =
    (statusQuery.isError && Boolean(statusQuery.data)) ||
    (targetsQuery.isError && Boolean(targetsQuery.data)) ||
    (profilesQuery.isError && Boolean(profilesQuery.data)) ||
    (allJobsResult.isError && jobs.length > 0 && !(allJobsResult.errors && allJobsResult.errors.length > 0)) ||
    (projectsQuery.isError && Boolean(projectsQuery.data));

  const hasPartialJobError = Boolean(
    allJobsResult.errors && allJobsResult.errors.length > 0 && jobs.length > 0
  );

  const recentJobs = jobs.slice(0, 5);

  const isJobsLoading = (allJobsResult.isLoading || projectsQuery.isLoading) && jobs.length === 0;
  const isJobsInitialError =
    (allJobsResult.isError || projectsQuery.isError) &&
    jobs.length === 0 &&
    !allJobsResult.isLoading &&
    !projectsQuery.isLoading;

  const jobColumns = [
    { key: 'id', header: 'Job ID', render: (j: Job) => j.id },
    { key: 'workflow', header: 'Workflow', render: (j: Job) => j.workflow },
    { key: 'profile', header: 'Profile', render: (j: Job) => j.profile },
    { key: 'state', header: 'State', render: (j: Job) => <StatusBadge state={j.state} /> },
    {
      key: 'created_at',
      header: 'Created',
      render: (j: Job) => <time dateTime={j.created_at}>{formatDate(j.created_at)}</time>,
    },
  ];

  const targetsData = targetsQuery.data;
  const isTargetsLoading = targetsQuery.isLoading && !targetsData;
  const isTargetsError = targetsQuery.isError && !targetsData;

  const targetList = targetsData ?? [];
  const totalTargets = targetList.length;
  const healthyTargets = targetList.filter((t) => t.healthy).length;
  const degradedTargets = targetList.filter((t) => !t.healthy).length;
  const openCircuitTargets = targetList.filter(
    (t) => deriveCircuitState(t.circuit_open_until) === 'circuit-open'
  ).length;

  const projectsData = projectsQuery.data;
  const isProjectsLoading = projectsQuery.isLoading && !projectsData;
  const isProjectsError = projectsQuery.isError && !projectsData;

  const projectList = projectsData ?? [];
  const totalProjects = projectList.length;
  const cleanProjects = projectList.filter((p) => p.clean).length;
  const dirtyProjects = projectList.filter((p) => !p.clean).length;

  const profilesData = profilesQuery.data;
  const isProfilesLoading = profilesQuery.isLoading && !profilesData;
  const isProfilesError = profilesQuery.isError && !profilesData;

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

      {hasPartialJobError && (
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
          Could not load jobs for all projects. Showing partial results.
        </div>
      )}

      {/* Area 1: System Status */}
      <Panel title="System Status" headingLevel="h2">
        {statusQuery.isLoading && !statusQuery.data ? (
          <div role="status" className="ff-text-sm ff-fg-subdued">
            Loading system status...
          </div>
        ) : statusQuery.isError && !statusQuery.data ? (
          <div role="alert" className="ff-text-sm ff-fg-red">
            Failed to load system status.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 'var(--space-md)' }}>
            <div className={styles.metricChip} style={{ flexDirection: 'column', alignItems: 'flex-start', padding: 'var(--space-sm)' }}>
              <span className={styles.metricLabel}>Workers</span>
              <span className={styles.metricValue} style={{ fontSize: 'var(--type-text-xl-size)' }}>
                {statusQuery.data?.workers ?? 0}
              </span>
            </div>
            <div className={styles.metricChip} style={{ flexDirection: 'column', alignItems: 'flex-start', padding: 'var(--space-sm)' }}>
              <span className={styles.metricLabel}>Active Jobs</span>
              <span className={styles.metricValue} style={{ fontSize: 'var(--type-text-xl-size)' }}>
                {statusQuery.data?.active_jobs ?? 0}
              </span>
            </div>
            <div className={styles.metricChip} style={{ flexDirection: 'column', alignItems: 'flex-start', padding: 'var(--space-sm)' }}>
              <span className={styles.metricLabel}>Queued Jobs</span>
              <span className={styles.metricValue} style={{ fontSize: 'var(--type-text-xl-size)' }}>
                {statusQuery.data?.queued_jobs ?? 0}
              </span>
            </div>
          </div>
        )}
      </Panel>

      {/* Area 2: Recent Jobs */}
      <Panel title="Recent Jobs" supportingText="Latest 5 jobs across all projects" headingLevel="h2">
        {isJobsLoading ? (
          <div role="status" className="ff-text-sm ff-fg-subdued">
            Loading recent jobs...
          </div>
        ) : isJobsInitialError ? (
          <div role="alert" className="ff-text-sm ff-fg-red">
            Failed to load recent jobs.
          </div>
        ) : recentJobs.length === 0 ? (
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
          {isTargetsLoading ? (
            <div role="status" className="ff-text-sm ff-fg-subdued">
              Loading target health...
            </div>
          ) : isTargetsError ? (
            <div role="alert" className="ff-text-sm ff-fg-red">
              Failed to load target health.
            </div>
          ) : (
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
          )}
        </Panel>

        {/* Area 4: Projects Summary */}
        <Panel title="Projects Summary" headingLevel="h3">
          {isProjectsLoading ? (
            <div role="status" className="ff-text-sm ff-fg-subdued">
              Loading projects summary...
            </div>
          ) : isProjectsError ? (
            <div role="alert" className="ff-text-sm ff-fg-red">
              Failed to load projects summary.
            </div>
          ) : (
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
          )}
        </Panel>

        {/* Area 5: Profiles Summary */}
        <Panel title="Profiles Summary" headingLevel="h3">
          {isProfilesLoading ? (
            <div role="status" className="ff-text-sm ff-fg-subdued">
              Loading profiles summary...
            </div>
          ) : isProfilesError ? (
            <div role="alert" className="ff-text-sm ff-fg-red">
              Failed to load profiles summary.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span className={styles.metricLabel}>Default Profile</span>
                <span className={styles.metricValue}>{profilesData?.default || 'None'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span className={styles.metricLabel}>Available Profiles</span>
                <span className={styles.metricValue}>{profilesData?.available ? profilesData.available.length : 0}</span>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
};
