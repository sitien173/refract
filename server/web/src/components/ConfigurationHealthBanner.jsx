import Alert from './Alert'

export default function ConfigurationHealthBanner({ health }) {
  if (!health || health.valid) return null

  return (
    <Alert tone="error" title="Configuration invalid — showing last-known-good values">
      <p>
        The global configuration is invalid. Cached catalog values remain visible, but new job submissions are blocked until the source is corrected.
      </p>
      <div className="configuration-health-revision">
        <span className="caption">Last-known-good revision</span>
        <code>{health.last_known_good_revision || 'Unavailable'}</code>
      </div>
    </Alert>
  )
}
