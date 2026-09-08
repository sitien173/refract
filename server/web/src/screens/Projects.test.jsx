import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import Projects from './Projects'

vi.mock('../api', () => ({
  getProjects: vi.fn(),
  getProject: vi.fn(),
  getProjectJobs: vi.fn(),
  getConfiguration: vi.fn().mockResolvedValue({ valid: true }),
}))

describe('Projects screen', () => {
  const mockProjects = [
    {
      id: 'proj-alpha',
      alias: 'Alpha Workspace',
      root: '/workspace/alpha',
    },
    {
      id: 'proj-beta',
      alias: 'Beta Workspace',
      root: '/workspace/beta',
    },
  ]

  beforeEach(() => {
    vi.mocked(api.getConfiguration).mockResolvedValue({ valid: true })
    vi.mocked(api.getProjects).mockResolvedValue(mockProjects)
    vi.mocked(api.getProject).mockImplementation(async (id) => ({
      project: { id, alias: id, root: `/workspace/${id}` },
      configuration: { project_default_profile: 'default' },
    }))
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
  })

  it('renders registered projects list with hydration', async () => {
    render(<Projects />)

    expect(await screen.findByText('Alpha Workspace')).toBeInTheDocument()
    expect(screen.getByText('/workspace/alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta Workspace')).toBeInTheDocument()
    expect(screen.getByText('/workspace/beta')).toBeInTheDocument()
  })

  it('renders invalid configuration health banner and last-known-good revision while cached projects remain visible', async () => {
    vi.mocked(api.getConfiguration).mockResolvedValue({
      valid: false,
      last_known_good_revision: 'rev-projects-lkg-001',
    })

    render(<Projects />)

    expect(await screen.findByText('Configuration invalid — showing last-known-good values')).toBeInTheDocument()
    expect(screen.getByText('rev-projects-lkg-001')).toBeInTheDocument()
    expect(screen.getByText('Alpha Workspace')).toBeInTheDocument()
    expect(screen.getByText('/workspace/alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta Workspace')).toBeInTheDocument()
  })

  it('exposes sortable headers and responsive priority classes on projects table', async () => {
    render(<Projects />)
    expect(await screen.findByText('Alpha Workspace')).toBeInTheDocument()

    const aliasHeader = screen.getByRole('columnheader', { name: /Alias/i })
    expect(aliasHeader.className).toMatch(/col-priority-primary/)

    const rootHeader = screen.getByRole('columnheader', { name: /Workspace root/i })
    expect(rootHeader.className).toMatch(/col-priority-tertiary/)

    // Sort descending by Alias
    const sortBtn = screen.getByRole('button', { name: /Sort by Alias/i })
    fireEvent.click(sortBtn) // asc: Alpha, Beta
    fireEvent.click(sortBtn) // desc: Beta, Alpha
    expect(aliasHeader).toHaveAttribute('aria-sort', 'descending')
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('Beta Workspace')
    expect(rows[1]).toHaveTextContent('Alpha Workspace')
  })
})
