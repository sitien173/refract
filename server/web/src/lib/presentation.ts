export type CircuitState = 'circuit-open' | 'circuit-closed' | 'circuit-unknown';

export function deriveCircuitState(circuitOpenUntil?: string | null): CircuitState {
  if (!circuitOpenUntil || circuitOpenUntil.trim() === '') {
    return 'circuit-closed';
  }

  const date = new Date(circuitOpenUntil);
  if (isNaN(date.getTime())) {
    return 'circuit-unknown';
  }

  if (date.getTime() > Date.now()) {
    return 'circuit-open';
  }

  return 'circuit-closed';
}

export function formatDate(isoString: string): string {
  if (!isoString || isoString.trim() === '') {
    return '—';
  }
  const date = new Date(isoString);
  if (isNaN(date.getTime())) {
    return '—';
  }
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}
