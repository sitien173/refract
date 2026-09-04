export default function Alert({ tone = 'info', title, children }) {
  return (
    <div className={`alert alert-${tone}`} role={tone === 'error' ? 'alert' : undefined}>
      <span className="alert-mark" aria-hidden="true" />
      <div>
        {title && <strong>{title}</strong>}
        {children && <p>{children}</p>}
      </div>
    </div>
  )
}
