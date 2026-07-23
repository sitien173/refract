import React from 'react';
import { useTargets } from '../lib/queries';
import { deriveCircuitState } from '../lib/presentation';
import { DataTable } from '../components/DataTable';
import { StatusBadge } from '../components/StatusBadge';
import { EmptyState } from '../components/EmptyState';
import { Target } from '../lib/types';
import styles from '../styles/app.module.css';

export const Targets: React.FC = () => {
  const { data: targets, isLoading, isError } = useTargets();

  if (isLoading && !targets) {
    return (
      <div role="status" aria-live="polite" className={styles.placeholderPanel}>
        <p className="ff-text-md ff-fg-subdued">Loading targets...</p>
      </div>
    );
  }

  if (isError && !targets) {
    return (
      <div role="alert" aria-live="polite" className={styles.placeholderPanel}>
        <p className="ff-text-md ff-fg-red">Failed to load targets.</p>
      </div>
    );
  }

  const targetList = targets ?? [];

  const columns = [
    { key: 'id', header: 'Target ID', render: (t: Target) => t.id },
    { key: 'model', header: 'Model', render: (t: Target) => t.model },
    {
      key: 'capabilities',
      header: 'Capabilities',
      render: (t: Target) => t.capabilities.join(', ') || '—',
    },
    {
      key: 'active',
      header: 'Active / Capacity',
      render: (t: Target) => `${t.active} / ${t.max_concurrency}`,
    },
    {
      key: 'healthy',
      header: 'Health',
      render: (t: Target) => (
        <StatusBadge state={t.healthy ? 'healthy' : 'degraded'} />
      ),
    },
    {
      key: 'circuit',
      header: 'Circuit State',
      render: (t: Target) => (
        <StatusBadge state={deriveCircuitState(t.circuit_open_until)} />
      ),
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
      {isError && targets && (
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

      {targetList.length === 0 ? (
        <EmptyState message="No targets found." />
      ) : (
        <DataTable
          caption="Targets List Table"
          columns={columns}
          rows={targetList}
          getRowKey={(t) => t.id}
        />
      )}
    </div>
  );
};
