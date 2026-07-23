import React from 'react';
import { useProfiles } from '../lib/queries';
import { Panel } from '../components/Panel';
import { DataTable } from '../components/DataTable';
import { EmptyState } from '../components/EmptyState';
import styles from '../styles/app.module.css';

interface ProfileRow {
  name: string;
  isDefault: boolean;
}

export const Profiles: React.FC = () => {
  const { data: profilesData, isLoading, isError } = useProfiles();

  if (isLoading && !profilesData) {
    return (
      <div role="status" aria-live="polite" className={styles.placeholderPanel}>
        <p className="ff-text-md ff-fg-subdued">Loading profiles...</p>
      </div>
    );
  }

  if (isError && !profilesData) {
    return (
      <div role="alert" aria-live="polite" className={styles.placeholderPanel}>
        <p className="ff-text-md ff-fg-red">Failed to load profiles.</p>
      </div>
    );
  }

  const defaultProfile = profilesData?.default || '';
  const availableList = profilesData?.available ?? [];

  const rows: ProfileRow[] = availableList.map((name) => ({
    name,
    isDefault: name === defaultProfile,
  }));

  const columns = [
    { key: 'name', header: 'Profile Name', render: (r: ProfileRow) => r.name },
    {
      key: 'default',
      header: 'Role',
      render: (r: ProfileRow) =>
        r.isDefault ? <span className={styles.brandBadge}>Default</span> : '—',
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      {isError && profilesData && (
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

      {/* Default Profile Panel */}
      <Panel title="Default Profile" headingLevel="h2">
        {defaultProfile ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
            <span className="ff-text-lg" style={{ fontWeight: 600 }}>{defaultProfile}</span>
            <span className={styles.brandBadge}>Default</span>
          </div>
        ) : (
          <p className="ff-text-sm ff-fg-subdued">No default profile specified.</p>
        )}
      </Panel>

      {/* Available Profiles Panel */}
      <Panel title="Available Profiles" headingLevel="h2">
        {availableList.length === 0 ? (
          <EmptyState message="No profiles available." />
        ) : (
          <DataTable
            caption="Available Profiles Table"
            columns={columns}
            rows={rows}
            getRowKey={(r) => r.name}
          />
        )}
      </Panel>
    </div>
  );
};
