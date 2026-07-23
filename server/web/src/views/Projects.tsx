import React from 'react';
import { useProjects } from '../lib/queries';
import { formatDate } from '../lib/presentation';
import { DataTable } from '../components/DataTable';
import { EmptyState } from '../components/EmptyState';
import { Project } from '../lib/types';
import styles from '../styles/app.module.css';

export const Projects: React.FC = () => {
  const { data: projects, isLoading, isError } = useProjects();

  if (isLoading && !projects) {
    return (
      <div role="status" aria-live="polite" className={styles.placeholderPanel}>
        <p className="ff-text-md ff-fg-subdued">Loading projects...</p>
      </div>
    );
  }

  if (isError && !projects) {
    return (
      <div role="alert" aria-live="polite" className={styles.placeholderPanel}>
        <p className="ff-text-md ff-fg-red">Failed to load projects.</p>
      </div>
    );
  }

  const projectList = projects ?? [];

  const columns = [
    { key: 'alias', header: 'Alias', render: (p: Project) => p.alias },
    { key: 'root', header: 'Root Path', render: (p: Project) => p.root },
    {
      key: 'created_at',
      header: 'Created Time',
      render: (p: Project) => (
        <time dateTime={p.created_at}>{formatDate(p.created_at)}</time>
      ),
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
      {isError && projects && (
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

      {projectList.length === 0 ? (
        <EmptyState message="No projects found." />
      ) : (
        <DataTable
          caption="Projects List Table"
          columns={columns}
          rows={projectList}
          getRowKey={(p) => p.id}
        />
      )}
    </div>
  );
};
