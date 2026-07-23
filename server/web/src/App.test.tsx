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

  const routes = [
    { hash: '#/', title: 'Overview', activeName: /Overview/i },
    { hash: '#/projects', title: 'Projects', activeName: /Projects/i },
    { hash: '#/targets', title: 'Targets', activeName: /Targets/i },
    { hash: '#/profiles', title: 'Profiles', activeName: /Profiles/i },
  ];

  routes.forEach(({ hash, title }) => {
    it(`directly initializes hash ${hash}, asserts route title '${title}' and exact active navigation`, () => {
      window.location.hash = hash;
      render(<App />);

      expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();

      routes.forEach((r) => {
        const link = screen.getByRole('link', { name: r.activeName });
        if (r.hash === hash) {
          expect(link).toHaveClass(/navItemActive/);
        } else {
          expect(link).not.toHaveClass(/navItemActive/);
        }
      });
    });
  });

  it('asserts brand navigation returns to Overview without reload', async () => {
    window.location.hash = '#/projects';
    render(<App />);

    expect(screen.getByRole('heading', { level: 1, name: 'Projects' })).toBeInTheDocument();

    const brandLink = screen.getByRole('link', { name: /OpenMCP Console/i });
    fireEvent.click(brandLink);

    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/');
  });

  it('asserts unknown hash redirect (e.g. #/jobs) replaces hash with #/', async () => {
    window.location.hash = '#/jobs';
    render(<App />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/');
  });

  it('renders disabled Jobs semantics', () => {
    render(<App />);
    const jobsDisabledItem = screen.getByText('Jobs - Unavailable').closest('li');
    expect(jobsDisabledItem).toHaveAttribute('aria-disabled', 'true');
    expect(jobsDisabledItem?.querySelector('a')).toBeNull();
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
