import React from 'react'
import { useSettings, useOverview } from '../hooks/usePolling.js'

export function RuntimeView({ overview: propOverview = null }) {
  const { data: polledOverview } = useOverview({ enabled: !propOverview })
  const overview = propOverview || polledOverview
  const configuration = overview?.configuration

  const { data: settings, isLoading, error } = useSettings()

  if (isLoading && !settings) {
    return (
      <main
        role="main"
        data-testid="runtime-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          color: 'var(--text-description)',
          backgroundColor: 'var(--surface-neutral-01)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-sm)' }}>
          <div className="tds-spinner tds-spinner--sm" aria-hidden="true" />
          <span>Loading runtime settings...</span>
        </div>
      </main>
    )
  }

  if (error && !settings) {
    return (
      <main
        role="main"
        data-testid="runtime-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          backgroundColor: 'var(--surface-neutral-01)',
        }}
      >
        <div role="alert" className="tds-announcement tds-announcement--negative">
          <div className="tds-announcement__content">
            <p className="tds-announcement__title">Failed to load settings</p>
            <p className="tds-announcement__message">{error.message || 'Network error'}</p>
          </div>
        </div>
      </main>
    )
  }

  if (!settings) {
    return (
      <main
        role="main"
        data-testid="runtime-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          color: 'var(--text-description)',
          backgroundColor: 'var(--surface-neutral-01)',
        }}
      >
        <p>No runtime settings available.</p>
      </main>
    )
  }

  const daemon = settings.daemon || {}
  const logging = settings.logging || {}
  const isConfigValid = configuration?.valid ?? true
  const latestError = configuration?.latest_error || ''
  const lastKnownGood = configuration?.last_known_good_revision || ''

  return (
    <main
      role="main"
      data-testid="runtime-view"
      style={{
        flex: 1,
        padding: 'var(--padding-xl)',
        backgroundColor: 'var(--surface-neutral-01)',
        overflowY: 'auto',
      }}
    >
      <div style={{ marginBottom: 'var(--gap-xl)' }}>
        <h2
          style={{
            fontSize: 'var(--font-size-xl)',
            fontWeight: 'var(--font-weight-bold)',
            color: 'var(--text-default)',
            margin: '0 0 var(--gap-xs) 0',
          }}
        >
          Runtime
        </h2>
        <p
          style={{
            fontSize: 'var(--font-size-sm)',
            color: 'var(--text-description)',
            margin: 0,
          }}
        >
          Daemon status, configuration health, and logging parameters.
        </p>
      </div>

      {/* Configuration Health Card */}
      <div
        style={{
          marginBottom: 'var(--gap-xl)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-card)',
          padding: 'var(--padding-lg)',
          backgroundColor: isConfigValid ? 'var(--surface-neutral-02)' : 'var(--surface-negative)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 'var(--gap-sm)',
          }}
        >
          <h3
            style={{
              fontSize: 'var(--font-size-md)',
              fontWeight: 'var(--font-weight-semibold)',
              color: 'var(--text-default)',
              margin: 0,
            }}
          >
            Configuration Health
          </h3>
          <span
            className={`tds-tag ${
              isConfigValid ? 'tds-tag--positive' : 'tds-tag--negative'
            }`}
          >
            {isConfigValid ? 'Valid' : 'Invalid'}
          </span>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 'var(--gap-md)',
            fontSize: 'var(--font-size-sm)',
            color: 'var(--text-description)',
          }}
        >
          <div>
            <strong>Revision:</strong> {configuration?.revision || settings.revision || '-'}
          </div>
          <div>
            <strong>Source Path:</strong> {configuration?.source_path || settings.source_path || '-'}
          </div>
        </div>

        {!isConfigValid && (
          <div
            style={{
              marginTop: 'var(--gap-md)',
              padding: 'var(--padding-md)',
              backgroundColor: 'var(--surface-neutral-01)',
              borderRadius: 'var(--radius-card)',
              border: '1px solid var(--border-negative)',
            }}
          >
            <div style={{ color: 'var(--text-negative)', fontWeight: 'var(--font-weight-semibold)', marginBottom: 'var(--gap-xs)' }}>
              Latest Error:
            </div>
            <pre
              style={{
                margin: '0 0 var(--gap-sm) 0',
                fontFamily: 'monospace',
                fontSize: 'var(--font-size-xs)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                color: 'var(--text-negative)',
              }}
            >
              {latestError}
            </pre>
            {lastKnownGood && (
              <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-caption)' }}>
                <strong>Last Known Good Revision:</strong> {lastKnownGood}
              </div>
            )}
            <div style={{ marginTop: 'var(--gap-xs)', fontSize: 'var(--font-size-xs)', color: 'var(--text-caption)' }}>
              Configuration edits must be made directly in <code>.refract/config.toml</code>.
            </div>
          </div>
        )}
      </div>

      {/* Daemon Settings */}
      <div style={{ marginBottom: 'var(--gap-xl)' }}>
        <h3
          style={{
            fontSize: 'var(--font-size-lg)',
            fontWeight: 'var(--font-weight-semibold)',
            color: 'var(--text-default)',
            margin: '0 0 var(--gap-md) 0',
          }}
        >
          Daemon Settings
        </h3>
        <div
          className="tds-data-table-container"
          style={{
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-card)',
          }}
        >
          <div className="tds-data-table__wrapper">
            <table className="tds-data-table tds-data-table--compact">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Host
                  </td>
                  <td className="tds-data-table__text-cell">{daemon.host || '-'}</td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Port
                  </td>
                  <td className="tds-data-table__text-cell">{String(daemon.port ?? '-')}</td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Max Jobs
                  </td>
                  <td className="tds-data-table__text-cell">{String(daemon.max_jobs ?? '-')}</td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    History Turns
                  </td>
                  <td className="tds-data-table__text-cell">{String(daemon.history_turns ?? '-')}</td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    History Bytes
                  </td>
                  <td className="tds-data-table__text-cell">{String(daemon.history_bytes ?? '-')}</td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Default Profile
                  </td>
                  <td className="tds-data-table__text-cell">{daemon.default_profile || '-'}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Logging Settings */}
      <div>
        <h3
          style={{
            fontSize: 'var(--font-size-lg)',
            fontWeight: 'var(--font-weight-semibold)',
            color: 'var(--text-default)',
            margin: '0 0 var(--gap-md) 0',
          }}
        >
          Logging Settings
        </h3>
        <div
          className="tds-data-table-container"
          style={{
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-card)',
          }}
        >
          <div className="tds-data-table__wrapper">
            <table className="tds-data-table tds-data-table--compact">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Level
                  </td>
                  <td className="tds-data-table__text-cell">
                    <span className="tds-tag tds-tag--default">{logging.level || '-'}</span>
                  </td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Format
                  </td>
                  <td className="tds-data-table__text-cell">{logging.format || '-'}</td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    File
                  </td>
                  <td className="tds-data-table__text-cell">
                    {logging.file ? String(logging.file) : 'None (Console only)'}
                  </td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Console
                  </td>
                  <td className="tds-data-table__text-cell">{logging.console ? 'Enabled' : 'Disabled'}</td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Max Bytes
                  </td>
                  <td className="tds-data-table__text-cell">{String(logging.max_bytes ?? '-')}</td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Backup Count
                  </td>
                  <td className="tds-data-table__text-cell">{String(logging.backup_count ?? '-')}</td>
                </tr>
                <tr>
                  <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                    Capture Warnings
                  </td>
                  <td className="tds-data-table__text-cell">
                    {logging.capture_warnings ? 'Enabled' : 'Disabled'}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  )
}

export default RuntimeView
