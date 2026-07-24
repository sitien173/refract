import { describe, it, expect } from 'vitest';
import { deriveCircuitState, formatDate } from './presentation';

describe('presentation helpers', () => {
  describe('deriveCircuitState', () => {
    it('returns circuit-open for a valid future timestamp', () => {
      const future = new Date(Date.now() + 60000).toISOString();
      expect(deriveCircuitState(future)).toBe('circuit-open');
    });

    it('returns circuit-closed for an empty or undefined timestamp', () => {
      expect(deriveCircuitState('')).toBe('circuit-closed');
      expect(deriveCircuitState(null)).toBe('circuit-closed');
      expect(deriveCircuitState(undefined)).toBe('circuit-closed');
    });

    it('returns circuit-closed for an expired timestamp', () => {
      const past = new Date(Date.now() - 60000).toISOString();
      expect(deriveCircuitState(past)).toBe('circuit-closed');
    });

    it('returns circuit-unknown for an invalid non-empty timestamp', () => {
      expect(deriveCircuitState('invalid-date-string')).toBe('circuit-unknown');
    });
  });

  describe('formatDate', () => {
    it('formats ISO date string into readable representation', () => {
      const result = formatDate('2026-07-23T12:00:00Z');
      expect(result).toBeTruthy();
      expect(typeof result).toBe('string');
    });

    it('returns fallback for empty or invalid date', () => {
      expect(formatDate('')).toBe('—');
      expect(formatDate('invalid')).toBe('—');
    });
  });
});
