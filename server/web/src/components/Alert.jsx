export default function Alert({ tone = 'info', title, children, role }) {
  const alertRole = role || (tone === 'error' ? 'alert' : undefined)
  return (
    <div className={`alert alert-${tone}`} role={alertRole}>
      <span className="alert-mark" aria-hidden="true" />
      <div>
        {title && <strong>{title}</strong>}
        {children && <div className="alert-body">{children}</div>}
      </div>
    </div>
  )
}
