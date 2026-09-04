import { getConfiguration, getProfiles } from '../api'
import Alert from '../components/Alert'
import ConfigurationHealthBanner from '../components/ConfigurationHealthBanner'
import DataGrid from '../components/DataGrid'
import PageHeader from '../components/PageHeader'
import { useDashboardQuery } from '../hooks/useDashboardQuery'

export default function Profiles() {
  const { data, error, isLoading, refresh } = useDashboardQuery(getProfiles)
  const { data: configurationHealth, refresh: refreshConfigurationHealth } = useDashboardQuery(getConfiguration, { pollInterval: 5000 })

  const defaultProfile = data?.default || 'default'
  const available = data?.available || []

  const rows = available.map((name) => ({
    id: name,
    name,
    isDefault: name === defaultProfile,
  }))

  const columns = [
    {
      key: 'name',
      header: 'Profile identifier',
      width: '240px',
      render: (row) => <strong>{row.name}</strong>,
    },
    {
      key: 'isDefault',
      header: 'Default fallback',
      width: '180px',
      render: (row) => (
        <span className={`profile-tag ${row.isDefault ? 'profile-tag-default' : ''}`}>
          {row.isDefault ? 'Global default' : 'Profile'}
        </span>
      ),
    },
    {
      key: 'scope',
      header: 'Scope',
      width: '200px',
      render: () => <span>Global catalog</span>,
    },
  ]

  return (
    <div className="page">
      <PageHeader
        title="Profiles"
        description="Global workflow profiles and routing policy."
        actions={
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={() => {
              refresh()
              refreshConfigurationHealth()
            }}
            disabled={isLoading}
          >
            {isLoading ? 'Loading…' : 'Refresh'}
          </button>
        }
      />

      {error && !data && (
        <Alert tone="error" title="Unable to load profiles">
          {error.message || 'Failed to fetch global profiles.'}
        </Alert>
      )}
      <ConfigurationHealthBanner health={configurationHealth} />

      {error && data && (
        <Alert tone="warning" title="Showing previously loaded profiles">
          Background refresh failed. The profile table remains unchanged; retry when the daemon is available.
        </Alert>
      )}

      <DataGrid
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        emptyMessage="No global profiles found in configuration."
        ariaLabel="Global profiles table"
        isLoading={isLoading}
      />
    </div>
  )
}
