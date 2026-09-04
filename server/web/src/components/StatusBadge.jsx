export default function StatusBadge({ status = 'unknown', label }) {
  const tone = status === 'running' || status === 'succeeded' || status === 'healthy'
    ? 'success'
    : status === 'failed' || status === 'invalid'
      ? 'error'
      : status === 'queued' || status === 'unknown'
        ? 'neutral'
        : 'warning'
  return (
    <span className={`status-badge status-${tone}`}>
      <span className="status-icon" aria-hidden="true" />
      <span>{label || status}</span>
    </span>
  )
}
