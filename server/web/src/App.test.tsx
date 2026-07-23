import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { App } from './App';
import { ThemeToggle } from './components/ThemeToggle';

describe('AppShell and ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('renders static navigation buttons in sidebar', () => {
    render(<App />);
    expect(screen.getByRole('button', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Projects' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Jobs' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Targets' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Profiles' })).toBeInTheDocument();
  });

  it('toggles light/dark theme and updates localStorage', () => {
    render(<ThemeToggle />);
    const btn = screen.getByRole('button', { name: /Switch to/i });
    expect(btn).toBeInTheDocument();

    fireEvent.click(btn);
    const newTheme = document.documentElement.getAttribute('data-theme');
    expect(newTheme).toMatch(/dark|light/);
    expect(localStorage.getItem('theme')).toBe(newTheme);
  });

  it('handles blocked localStorage gracefully when toggling theme', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Access denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('Access denied');
    });

    render(<ThemeToggle />);
    const btn = screen.getByRole('button', { name: /Switch to/i });
    expect(btn).toBeInTheDocument();

    expect(() => fireEvent.click(btn)).not.toThrow();
    vi.restoreAllMocks();
  });
});
