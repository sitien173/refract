export default function PageHeader({
  title,
  description,
  badge,
  lastKnownGood,
  actions,
  backLink,
}) {
  const revision =
    typeof lastKnownGood === 'string'
      ? lastKnownGood
      : lastKnownGood?.revision || lastKnownGood?.last_known_good_revision

  return (
    <div className="page-header">
      <div className="page-header-content">
        {backLink && <div className="page-header-back">{backLink}</div>}
        <div className="page-header-title-row">
          <h2>{title}</h2>
          {badge}
        </div>
        {description && <p className="page-header-description">{description}</p>}
        {lastKnownGood && revision && (
          <div className="last-known-good-chip" role="status">
            <span className="eyebrow">Last-known-good</span>
            <code>{revision}</code>
          </div>
        )}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  )
}
