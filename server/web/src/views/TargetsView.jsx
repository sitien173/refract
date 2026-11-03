import React from 'react'
import { useTargets, useProfiles } from '../hooks/usePolling.js'

export function TargetsView() {
  const {
    data: targets,
    isLoading: isTargetsLoading,
    error: targetsError,
  } = useTargets()

  const {
    data: profilesData,
    isLoading: isProfilesLoading,
    error: profilesError,
  } = useProfiles()

  const isLoading = (isTargetsLoading && !targets) || (isProfilesLoading && !profilesData)
  const error = targetsError || profilesError

  if (isLoading) {
    return (
      <main
        role="main"
        data-testid="targets-view"
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
          <span>Loading targets and profiles...</span>
        </div>
      </main>
    )
  }

  if ((targetsError && !targets) || (profilesError && !profilesData)) {
    return (
      <main
        role="main"
        data-testid="targets-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          backgroundColor: 'var(--surface-neutral-01)',
        }}
      >
        <div role="alert" className="tds-announcement tds-announcement--negative">
          <div className="tds-announcement__content">
            <p className="tds-announcement__title">Failed to load targets</p>
            <p className="tds-announcement__message">{error.message || 'Network error'}</p>
          </div>
        </div>
      </main>
    )
  }

  const targetList = Array.isArray(targets) ? targets : []
  const profilesList = Array.isArray(profilesData?.profiles) ? profilesData.profiles : []

  if (targetList.length === 0 && profilesList.length === 0) {
    return (
      <main
        role="main"
        data-testid="targets-view"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          color: 'var(--text-description)',
          backgroundColor: 'var(--surface-neutral-01)',
        }}
      >
        <p>No targets configured.</p>
      </main>
    )
  }

  return (
    <main
      role="main"
      data-testid="targets-view"
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
          Targets
        </h2>
        <p
          style={{
            fontSize: 'var(--font-size-sm)',
            color: 'var(--text-description)',
            margin: '0 0 var(--gap-md) 0',
          }}
        >
          Active execution targets, breaker health, and concurrency.
        </p>

        {targetList.length === 0 ? (
          <p style={{ color: 'var(--text-description)', fontSize: 'var(--font-size-sm)' }}>
            No execution targets configured.
          </p>
        ) : (
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
                    <th>Target</th>
                    <th>Backend</th>
                    <th>Model</th>
                    <th>Isolation</th>
                    <th>Read-only</th>
                    <th>Concurrency</th>
                    <th>Breaker State</th>
                    <th>Cooldown</th>
                    <th>Probing</th>
                    <th>Health</th>
                  </tr>
                </thead>
                <tbody>
                  {targetList.map((target) => {
                    let breakerVariant = 'tds-tag--default'
                    if (target.breaker_state === 'closed') breakerVariant = 'tds-tag--positive'
                    else if (target.breaker_state === 'open') breakerVariant = 'tds-tag--negative'
                    else if (target.breaker_state === 'half_open') breakerVariant = 'tds-tag--intermediate'

                    return (
                      <tr key={target.id}>
                        <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                          {target.id}
                        </td>
                        <td className="tds-data-table__text-cell">{target.backend || '-'}</td>
                        <td className="tds-data-table__text-cell">{target.model || '-'}</td>
                        <td className="tds-data-table__text-cell">
                          <span className={`tds-tag ${target.isolated ? 'tds-tag--intermediate' : 'tds-tag--default'}`}>
                            {target.isolated ? 'Isolated' : 'Shared'}
                          </span>
                        </td>
                        <td className="tds-data-table__text-cell">
                          <span className={`tds-tag ${target.read_only ? 'tds-tag--positive' : 'tds-tag--default'}`}>
                            {target.read_only ? 'Read-only' : 'Read-write'}
                          </span>
                        </td>
                        <td className="tds-data-table__text-cell">
                          {target.active} / {target.max_concurrency}
                        </td>
                        <td className="tds-data-table__text-cell">
                          <span className={`tds-tag ${breakerVariant}`}>
                            {target.breaker_state}
                          </span>
                        </td>
                        <td className="tds-data-table__text-cell">{target.cooldown_s}s</td>
                        <td className="tds-data-table__text-cell">
                          {target.probing ? 'Yes' : 'No'}
                        </td>
                        <td className="tds-data-table__text-cell">
                          <span className={`tds-tag ${target.healthy ? 'tds-tag--positive' : 'tds-tag--negative'}`}>
                            {target.healthy ? 'Healthy' : 'Unhealthy'}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop: 'var(--gap-2xl)' }}>
        <h2
          style={{
            fontSize: 'var(--font-size-xl)',
            fontWeight: 'var(--font-weight-bold)',
            color: 'var(--text-default)',
            margin: '0 0 var(--gap-xs) 0',
          }}
        >
          Profile Routing Matrix
        </h2>
        <p
          style={{
            fontSize: 'var(--font-size-sm)',
            color: 'var(--text-description)',
            margin: '0 0 var(--gap-md) 0',
          }}
        >
          Catalog workflows, fallback chains, and profile sources.
        </p>

        {profilesList.length === 0 ? (
          <p style={{ color: 'var(--text-description)', fontSize: 'var(--font-size-sm)' }}>
            No profile configurations found.
          </p>
        ) : (
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
                    <th>Profile</th>
                    <th>Workflow</th>
                    <th>Ordered Target Chain</th>
                    <th>Timeout</th>
                    <th>Source Label</th>
                  </tr>
                </thead>
                <tbody>
                  {profilesList.flatMap((prof) => {
                    const effective = prof.effective || {}
                    const workflows = Object.keys(effective)
                    const sources = prof.sources || {}

                    if (workflows.length === 0) {
                      return [
                        <tr key={prof.id}>
                          <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                            {prof.id}
                          </td>
                          <td className="tds-data-table__text-cell" colSpan={4}>
                            No workflows configured
                          </td>
                        </tr>,
                      ]
                    }

                    return workflows.map((wf) => {
                      const selection = effective[wf] || {}
                      const targets = selection.targets || []
                      const timeoutS = selection.timeout_s
                      const source = sources[wf] || 'global'

                      return (
                        <tr key={`${prof.id}-${wf}`}>
                          <td className="tds-data-table__text-cell" style={{ fontWeight: 'var(--font-weight-medium)' }}>
                            {prof.id}
                          </td>
                          <td className="tds-data-table__text-cell">{wf}</td>
                          <td className="tds-data-table__text-cell">
                            {targets.length > 0 ? (
                              <span>{targets.join(' → ')}</span>
                            ) : (
                              <span style={{ color: 'var(--text-disabled)' }}>none</span>
                            )}
                          </td>
                          <td className="tds-data-table__text-cell">
                            {timeoutS ? `${timeoutS}s` : '-'}
                          </td>
                          <td className="tds-data-table__text-cell">
                            <span
                              className={`tds-tag ${
                                source === 'project' ? 'tds-tag--intermediate' : 'tds-tag--default'
                              }`}
                            >
                              {source}
                            </span>
                          </td>
                        </tr>
                      )
                    })
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}

export default TargetsView
