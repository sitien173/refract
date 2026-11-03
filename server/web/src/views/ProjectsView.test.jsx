import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { ProjectsView } from './ProjectsView.jsx'
import * as api from '../api.js'

describe('ProjectsView', () => {
  const mockProjectsList = [
    {
      id: 'proj-alpha',
      alias: 'Alpha Project',
      root: '/workspace/alpha',
      created_at: '2026-11-01T10:00:00Z',
      job_counts: 12,
    },
    {
      id: 'proj-beta',
      alias: 'Beta Project',
      root: '/workspace/beta',
      created_at: '2026-11-02T11:00:00Z',
    },
  ]

  const mockProjectDetail = {
    project: {
      id: 'proj-alpha',
      alias: 'Alpha Project',
      root: '/workspace/alpha',
      created_at: '2026-11-01T10:00:00Z',
    },
    configuration: {
      global_default_profile: 'default',
      project_default_profile: 'custom-profile',
      profiles: [
        {
          id: 'custom-profile',
          parent: { value: 'default', source: 'global' },
          effective: {
            deliberate: { targets: ['target-pro', 'target-flash'], timeout_s: 300 },
            quick: { targets: ['target-flash'], timeout_s: 60 },
          },
          sources: {
            deliberate: 'project',
            quick: 'global',
          },
          declared: {},
          inherited: {},
        },
      ],
    },
  }

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders loading state when fetching projects', async () => {
    vi.spyOn(api, 'fetchProjects').mockImplementation(() => new Promise(() => {}))
    render(<ProjectsView />)
    expect(screen.getByText(/loading projects/i)).toBeInTheDocument()
  })

  it('renders empty state when projects list is empty', async () => {
    vi.spyOn(api, 'fetchProjects').mockResolvedValue([])
    render(<ProjectsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText(/no projects found/i)).toBeInTheDocument()
  })

  it('renders error state when fetch projects fails', async () => {
    vi.spyOn(api, 'fetchProjects').mockRejectedValue(new Error('Network error'))
    render(<ProjectsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/network error/i)).toBeInTheDocument()
  })

  it('renders project table with alias, path or id, and job counts if provided', async () => {
    vi.spyOn(api, 'fetchProjects').mockResolvedValue(mockProjectsList)
    render(<ProjectsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('Alpha Project')).toBeInTheDocument()
    expect(screen.getByText('/workspace/alpha')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()

    expect(screen.getByText('Beta Project')).toBeInTheDocument()
    expect(screen.getByText('/workspace/beta')).toBeInTheDocument()
    expect(screen.getByText('proj-alpha')).toBeInTheDocument()
  })

  it('renders project detail with global and project default profiles and per-workflow target chains with source attribution', async () => {
    vi.spyOn(api, 'fetchProject').mockResolvedValue(mockProjectDetail)
    render(<ProjectsView projectId="proj-alpha" />)

    await act(async () => {
      await Promise.resolve()
    })

    // Project metadata
    expect(screen.getByText('Alpha Project')).toBeInTheDocument()
    expect(screen.getByText('/workspace/alpha')).toBeInTheDocument()

    // Default profiles
    expect(screen.getByText(/global default profile/i)).toBeInTheDocument()
    expect(screen.getByText(/project default profile/i)).toBeInTheDocument()
    expect(screen.getAllByText('custom-profile').length).toBeGreaterThanOrEqual(1)

    // Workflow target chain & source attribution
    expect(screen.getByText('deliberate')).toBeInTheDocument()
    expect(screen.getByText(/target-pro/)).toBeInTheDocument()
    expect(screen.getAllByText(/target-flash/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/project/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/global/i).length).toBeGreaterThanOrEqual(1)
  })

  it('renders inline not-found state for unknown project id', async () => {
    const err = new Error('Unknown project')
    err.status = 404
    vi.spyOn(api, 'fetchProject').mockRejectedValue(err)
    render(<ProjectsView projectId="proj-nonexistent" />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText(/project not found/i)).toBeInTheDocument()
    expect(screen.getByText(/proj-nonexistent/i)).toBeInTheDocument()
  })

  it('STRICT INVARIANT: contains no form, no non-filter input, and no mutating button', async () => {
    vi.spyOn(api, 'fetchProjects').mockResolvedValue(mockProjectsList)
    const { container } = render(<ProjectsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(container.querySelectorAll('form').length).toBe(0)
    container.querySelectorAll('input').forEach((input) => {
      expect(['checkbox', 'radio', 'search'].includes(input.getAttribute('type'))).toBe(true)
    })
    container.querySelectorAll('button').forEach((button) => {
      expect(button.getAttribute('type') || 'button').toBe('button')
    })
  })
})
