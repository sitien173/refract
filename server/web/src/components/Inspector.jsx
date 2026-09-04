export function SourceChip({ source }) {
  if (!source) return null
  const normalized = String(source).toLowerCase()
  let label = source
  let chipClass = 'source-neutral'
  if (normalized === 'project') {
    label = 'Repository'
    chipClass = 'source-repository'
  } else if (normalized === 'global') {
    label = 'Global'
    chipClass = 'source-global'
  }

  return (
    <span className={`source-chip ${chipClass}`} title={`Sourced from ${label}`}>
      <span className="source-chip-mark" aria-hidden="true" />
      <span>{label}</span>
    </span>
  )
}

export function InspectorRow({ label, value, children }) {
  return (
    <div className="inspector-row">
      <span className="inspector-label">{label}</span>
      <div className="inspector-value">{children || <code>{String(value ?? '')}</code>}</div>
    </div>
  )
}

export default function Inspector({
  title,
  description,
  source,
  onClose,
  children,
  actions,
}) {
  return (
    <aside className="inspector-panel" aria-label={`Inspector: ${title}`}>
      <div className="inspector-header">
        <div className="inspector-title-area">
          <span className="eyebrow">Inspector</span>
          <h3>{title}</h3>
          {description && <p className="inspector-description">{description}</p>}
        </div>
        <div className="inspector-header-meta">
          {source && <SourceChip source={source} />}
          {onClose && (
            <button
              type="button"
              className="inspector-close-button"
              aria-label="Close inspector"
              onClick={onClose}
            >
              ✕
            </button>
          )}
        </div>
      </div>
      <div className="inspector-body">{children}</div>
      {actions && <div className="inspector-actions">{actions}</div>}
    </aside>
  )
}
