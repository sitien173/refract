export default function StatusBadge({ status = 'unknown', label }) {
  const normalized = String(status || '').toLowerCase()
  let tone = 'neutral'
  let stateClass = 'state-unknown'

  if (normalized === 'running' || normalized === 'succeeded' || normalized === 'healthy' || normalized === 'valid') {
    tone = 'success'
    stateClass = 'state-healthy'
  } else if (
    normalized === 'circuit_open' ||
    normalized === 'circuit-open' ||
    normalized === 'circuitopen' ||
    normalized.startsWith('circuit')
  ) {
    tone = 'warning'
    stateClass = 'state-circuit-open'
  } else if (normalized === 'failed' || normalized === 'invalid' || normalized === 'unhealthy' || normalized === 'error') {
    tone = 'error'
    stateClass = 'state-unhealthy'
  } else if (normalized === 'queued' || normalized === 'idle' || normalized === 'stopping' || normalized === 'unknown') {
    tone = 'neutral'
    stateClass = 'state-neutral'
  } else {
    tone = 'warning'
    stateClass = 'state-warning'
  }

  const displayText = label || (normalized === 'circuit-open' ? 'Circuit open' : status)

  return (
    <span className={`status-badge status-${tone} ${stateClass}`}>
      <span className={`status-icon ${stateClass}-icon`} aria-hidden="true" />
      <span>{displayText}</span>
    </span>
  )
}
