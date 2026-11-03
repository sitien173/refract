import React from 'react'

export function StatusStrip({ overview, isStale, error }) {
  const daemon = overview?.daemon
  const configuration = overview?.configuration
  const unhealthyTargets = overview?.unhealthy_targets ?? 0

  const isDisconnected = Boolean(error || !daemon)

  return (
    <header
      role="banner"
      data-testid="status-strip"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--padding-sm) var(--padding-lg)',
        backgroundColor: 'var(--surface-neutral-01)',
        borderBottom: '1px solid var(--border-subtle)',
        fontFamily: 'var(--font-family)',
        fontSize: 'var(--font-size-xs)',
        color: 'var(--text-default)',
        minHeight: '40px',
        boxSizing: 'border-box',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-md)' }}>
        <span style={{ fontWeight: 'var(--font-weight-bold)' }}>Refract</span>

        {isDisconnected ? (
          <span className="tds-tag tds-tag--sm tds-tag--negative">
            Disconnected
          </span>
        ) : (
          <span className="tds-tag tds-tag--sm tds-tag--positive">
            {daemon.status || 'Running'}
          </span>
        )}

        {isStale && (
          <span className="tds-tag tds-tag--sm tds-tag--intermediate">
            Data stale
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-lg)' }}>
        {!isDisconnected && (
          <>
            <span>{daemon.active_jobs ?? 0} active</span>
            <span style={{ color: 'var(--border-strong)' }}>|</span>
            <span>{daemon.queued_jobs ?? 0} queued</span>
            <span style={{ color: 'var(--border-strong)' }}>|</span>
            <span>
              {unhealthyTargets > 0
                ? `${unhealthyTargets} unhealthy target${unhealthyTargets === 1 ? '' : 's'}`
                : 'All targets healthy'}
            </span>
            <span style={{ color: 'var(--border-strong)' }}>|</span>
            <span>
              Config: {configuration?.revision ? `rev-${configuration.revision}` : (configuration?.valid ? 'Valid' : 'Unknown')}
            </span>
          </>
        )}
      </div>
    </header>
  )
}
