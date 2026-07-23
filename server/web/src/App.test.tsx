import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { App } from './App';
import { ThemeToggle } from './components/ThemeToggle';
import * as api from './lib/api';

describe('AppShell, Routing and ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    window.location.hash = '#/';
  });

  const routes = [
    { hash: '#/', title: 'Overview', activeName: /Overview/i },
    { hash: '#/projects', title: 'Projects', activeName: /Projects/i },
    { hash: '#/jobs', title: 'Jobs', activeName: /^Jobs$/i },
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

  it('asserts unknown hash redirect (e.g. #/unknown) replaces hash with #/', async () => {
    window.location.hash = '#/unknown';
    render(<App />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/');
  });

  it('renders active Jobs nav item when navigating to #/jobs', () => {
    window.location.hash = '#/jobs';
    render(<App />);
    const jobsLink = screen.getByRole('link', { name: /^Jobs$/i });
    expect(jobsLink).toBeInTheDocument();
    expect(jobsLink).toHaveClass(/navItemActive/);
  });

  it('initializes real HashRouter at #/jobs?selected=<encoded-id>, confirms Jobs page title remains sole h1, and Job Details h2 opens for decoded selection', async () => {
    const rawId = 'job/test-encoded&id=1';
    const encodedId = encodeURIComponent(rawId);

    vi.spyOn(api, 'fetchProjects').mockResolvedValue([]);
    vi.spyOn(api, 'fetchJob').mockImplementation((id) =>
      Promise.resolve({
        id,
        workflow: 'test-wf',
        profile: 'dev',
        project_id: 'p1',
        state: 'running',
        context_key: '',
        base_commit: 'abc',
        target_id: '',
        attempts: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        result: { text: '', commit: 'def', error: '' },
      } as any)
    );
    vi.spyOn(api, 'fetchJobEvents').mockResolvedValue([]);

    window.location.hash = `#/jobs?selected=${encodedId}`;
    render(<App />);

    const h1s = await screen.findAllByRole('heading', { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0]).toHaveTextContent('Jobs');

    const h2 = await screen.findByRole('heading', { level: 2, name: 'Job Details' });
    expect(h2).toBeInTheDocument();
    expect(await screen.findByText(rawId)).toBeInTheDocument();
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
