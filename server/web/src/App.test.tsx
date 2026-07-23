import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { App } from './App';
import { ThemeToggle } from './components/ThemeToggle';

describe('AppShell and ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    window.history.pushState({}, '', '/dashboard/');
  });

  it('renders navigation links in sidebar', () => {
    render(<App />);
    expect(screen.getAllByText('Overview').length).toBeGreaterThan(0);
    expect(screen.getByText('Projects')).toBeInTheDocument();
    expect(screen.getByText('Jobs')).toBeInTheDocument();
    expect(screen.getByText('Targets')).toBeInTheDocument();
    expect(screen.getByText('Profiles')).toBeInTheDocument();
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
});
