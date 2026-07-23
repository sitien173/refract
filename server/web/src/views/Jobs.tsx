import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAllJobs } from '../lib/queries';
import { DataTable, Column } from '../components/DataTable';
import { StatusBadge } from '../components/StatusBadge';
import { EmptyState } from '../components/EmptyState';
import { Inspector } from '../components/Inspector';
import { Job } from '../lib/types';
import styles from '../styles/app.module.css';

export const Jobs: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get('selected') || '';

  const [stateFilter, setStateFilter] = React.useState<string>('all');

  const filterRef = React.useRef<HTMLSelectElement>(null);
  const buttonRefs = React.useRef<Map<string, HTMLButtonElement>>(new Map());
  const prevSelectedIdRef = React.useRef<string>(selectedId);

  const {
    jobs,
    isInitialLoading,
    isInitialError,
    hasPartialFailure,
    hasRefetchError,
    projectsQuery,
  } = useAllJobs();

  React.useEffect(() => {
    if (prevSelectedIdRef.current && !selectedId) {
      const closedId = prevSelectedIdRef.current;
      const btn = buttonRefs.current.get(closedId);
      if (btn && document.body.contains(btn)) {
        btn.focus();
      } else if (filterRef.current) {
        filterRef.current.focus();
      }
    }
    prevSelectedIdRef.current = selectedId;
  }, [selectedId]);

  const projectsMap = React.useMemo(() => {
    const map = new Map<string, string>();
    projectsQuery.data?.forEach((p) => map.set(p.id, p.alias));
    return map;
  }, [projectsQuery.data]);

  const filteredJobs = React.useMemo(() => {
    if (stateFilter === 'all') return jobs;
    return jobs.filter((j) => j.state === stateFilter);
  }, [jobs, stateFilter]);

  const handleSelectJob = (id: string) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('selected', id);
    setSearchParams(nextParams);
  };

  const handleCloseInspector = () => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('selected');
    setSearchParams(nextParams, { replace: true });
  };

  const columns: Column<Job>[] = [
    {
      key: 'id',
      header: 'Job ID',
      render: (job) => (
        <button
          type="button"
          ref={(el) => {
            if (el) buttonRefs.current.set(job.id, el);
            else buttonRefs.current.delete(job.id);
          }}
          aria-label={`Open job ${job.id}`}
          className={styles.openJobBtn}
          onClick={() => handleSelectJob(job.id)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleSelectJob(job.id);
            }
          }}
        >
          Open job {job.id}
        </button>
      ),
    },
    {
      key: 'project',
      header: 'Project',
      render: (job) => projectsMap.get(job.project_id) || job.project_id,
    },
    {
      key: 'workflow',
      header: 'Workflow',
      render: (job) => job.workflow,
    },
    {
      key: 'profile',
      header: 'Profile',
      render: (job) => job.profile,
    },
    {
      key: 'state',
      header: 'State',
      render: (job) => <StatusBadge state={job.state} />,
    },
    {
      key: 'created_at',
      header: 'Created At',
      render: (job) => <time dateTime={job.created_at}>{job.created_at}</time>,
    },
  ];

  return (
    <div className={styles.jobsLayout} data-testid="jobs-view">
      <div className={styles.jobsMainArea}>
        <div className={styles.jobsControls}>
          <label htmlFor="state-filter" className={styles.jobsFilterLabel}>
            State
            <select
              id="state-filter"
              ref={filterRef}
              className={styles.jobsFilterSelect}
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
            >
              <option value="all">All States</option>
              <option value="queued">Queued</option>
              <option value="running">Running</option>
              <option value="succeeded">Succeeded</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
              <option value="interrupted">Interrupted</option>
            </select>
          </label>
        </div>

        {isInitialLoading && <p role="status">Loading jobs...</p>}

        {isInitialError && <p role="alert">Failed to load jobs.</p>}

        {!isInitialLoading && !isInitialError && (
          <>
            {hasPartialFailure && (
              <div className={styles.warningBanner}>
                Could not load jobs for all projects. Showing partial results.
              </div>
            )}

            {!hasPartialFailure && hasRefetchError && (
              <div className={styles.warningBanner}>
                Could not refresh. Showing last known data.
              </div>
            )}

            {hasPartialFailure && jobs.length === 0 ? (
              <EmptyState message="No jobs found in available results." />
            ) : jobs.length === 0 ? (
              <EmptyState message="No jobs found." />
            ) : filteredJobs.length === 0 ? (
              <EmptyState message="No jobs match this filter." />
            ) : (
              <DataTable
                caption="Jobs Table"
                columns={columns}
                rows={filteredJobs}
                getRowKey={(job) => job.id}
                onRowClick={(job) => handleSelectJob(job.id)}
                selectedRowKey={selectedId || undefined}
              />
            )}
          </>
        )}
      </div>

      {selectedId && (
        <Inspector jobId={selectedId} onClose={handleCloseInspector} />
      )}
    </div>
  );
};
