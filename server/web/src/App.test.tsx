import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { App } from './App';
import { ThemeToggle } from './components/ThemeToggle';

describe('AppShell, Routing and ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    window.location.hash = '#/';
  });

  it('renders HashRouter navigation items and active state', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();

    const overviewLink = screen.getByRole('link', { name: /Overview/i });
    expect(overviewLink).toBeInTheDocument();
    expect(overviewLink).toHaveClass(/navItemActive/);

    const jobsDisabledItem = screen.getByText('Jobs - Unavailable').closest('li');
    expect(jobsDisabledItem).toHaveAttribute('aria-disabled', 'true');
    expect(jobsDisabledItem?.querySelector('a')).toBeNull();
  });

  it('navigates between views via HashRouter links', async () => {
    render(<App />);

    const projectsLink = screen.getByRole('link', { name: /Projects/i });
    fireEvent.click(projectsLink);

    expect(await screen.findByRole('heading', { level: 1, name: 'Projects' })).toBeInTheDocument();

    const brandLink = screen.getByRole('link', { name: /OpenMCP Console/i });
    fireEvent.click(brandLink);

    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
  });

  it('redirects unknown hash route (e.g. #/jobs) to Overview', async () => {
    window.location.hash = '#/jobs';
    render(<App />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
  });

  it('renders nav icons as CSS masks inheriting currentColor', () => {
    render(<App />);
    const icon = screen.getByTestId('nav-icon-overview');
    expect(icon).toBeInTheDocument();
    expect(icon.tagName.toLowerCase()).toBe('span');
    expect(icon.style.getPropertyValue('--icon-url')).toMatch(
      /url\(.*(?:activity\.svg|data:image\/svg\+xml)/
    );
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
