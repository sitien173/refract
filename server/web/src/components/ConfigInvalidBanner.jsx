import React from 'react'

export function ConfigInvalidBanner({ configuration }) {
  if (!configuration || configuration.valid !== false) {
    return null
  }

  const latestError = configuration.latest_error || 'Configuration validation failed.'
  const lastKnownGood = configuration.last_known_good_revision || 'none'
  const sourceFile = configuration.source_path || '.refract/config.toml'

  return (
    <div
      role="alert"
      data-testid="config-invalid-banner"
      className="tds-announcement tds-announcement--error"
      style={{
        borderBottom: '1px solid var(--border-negative)',
        borderRadius: 0,
      }}
    >
      <div className="tds-announcement__content">
        <p className="tds-announcement__title">Configuration invalid</p>
        <p className="tds-announcement__message">
          {latestError} (Last known good revision: {lastKnownGood}). Direct edits must be made in {sourceFile}.
        </p>
      </div>
    </div>
  )
}
