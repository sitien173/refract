import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import ProjectDetail from './ProjectDetail'

vi.mock('../api', () => ({
  getProject: vi.fn(),
  getProjectJobs: vi.fn(),
  getTaskGuide: vi.fn(),
}))

describe('ProjectDetail screen', () => {
  const mockProjectData = {
    project: {
      id: 'proj-demo',
      alias: 'Demo Workspace',
      root: '/home/user/workspace/demo',
      created_at: '2026-09-04T12:00:00Z',
    },
    configuration: {
      global_default_profile: 'default',
      project_default_profile: 'custom-profile',
      profiles: [
        {
          id: 'custom-profile',
          parent: { value: 'base-profile', source: 'project' },
          declared: {
            implement: {
              selection: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
              source: 'project',
            },
          },
          inherited: {
            consult: { targets: ['opus-consult'], max_attempts: 1, timeout_s: 60 },
          },
          effective: {
            consult: { targets: ['opus-consult'], max_attempts: 1, timeout_s: 60 },
            implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
          },
          sources: {
            consult: 'global',
            implement: 'project',
          },
        },
        {
          id: 'root-profile',
          parent: { value: null, source: 'global' },
          declared: {},
          inherited: {},
          effective: {
            review: { targets: ['reviewer-target'], max_attempts: 1, timeout_s: 90 },
          },
          sources: {
            review: 'global',
          },
        },
      ],
    },
    context_instructions: {
      consult: 'Always provide concise analysis',
    },
  }

  it('renders effective workflows without duplication and maps source names', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '/path/guide.json' })

    render(<ProjectDetail projectId="proj-demo" />)

    expect(await screen.findByText('Demo Workspace')).toBeInTheDocument()
    expect(screen.getByText('/home/user/workspace/demo')).toBeInTheDocument()

    // Check effective workflows (consult and implement)
    expect(screen.getByText('consult')).toBeInTheDocument()
    expect(screen.getByText('implement')).toBeInTheDocument()

    // Check source chips
    expect(screen.getByText('Repository')).toBeInTheDocument()
    expect(screen.getByText('Global')).toBeInTheDocument()

    // Ensure rows match effective list and not duplicates
    const consultWorkflowHeadings = screen.getAllByText('consult')
    expect(consultWorkflowHeadings.length).toBe(1)
  })

  it('suppresses source chip when parent profile is null in profile resolution tab', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)

    // Switch to profile resolution tab
    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    // For custom-profile, parent is base-profile (source project -> Repository)
    expect(screen.getByText('base-profile')).toBeInTheDocument()
    expect(screen.getAllByText('Repository').length).toBeGreaterThan(0)

    // Switch active profile to root-profile (parent is null)
    const select = screen.getByLabelText(/Select profile/i)
    fireEvent.change(select, { target: { value: 'root-profile' } })

    expect(screen.getByText('No parent')).toBeInTheDocument()
  })

  it('opens docked inspector on workflow row click', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)

    expect(await screen.findByText('consult')).toBeInTheDocument()

    const consultRow = screen.getByText('consult').closest('tr')
    fireEvent.click(consultRow)

    // Inspector should open
    expect(screen.getByRole('complementary', { name: /Inspector: Workflow: consult/i })).toBeInTheDocument()
    expect(screen.getByText('60 seconds')).toBeInTheDocument()
  })

  it('uses server inherited classification for overlapping self-extension rows', async () => {
    vi.mocked(api.getProject).mockResolvedValue({
      ...mockProjectData,
      configuration: {
        ...mockProjectData.configuration,
        profiles: [{
          ...mockProjectData.configuration.profiles[0],
          declared: {
            implement: mockProjectData.configuration.profiles[0].declared.implement,
          },
          inherited: {
            implement: { targets: ['opus-worker'], max_attempts: 1, timeout_s: 60 },
          },
          effective: {
            implement: { targets: ['opus-worker'], max_attempts: 1, timeout_s: 60 },
          },
          sources: { implement: 'global' },
        }],
      },
    })
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)
    const row = await screen.findByText('implement')
    fireEvent.click(row.closest('tr'))

    expect(screen.getByText('Inherited')).toBeInTheDocument()
  })

  it('displays error alert on project configuration load failure', async () => {
    const error = new Error('Invalid project configuration TOML')
    error.payload = { source_path: '/path/to/.openmcp/config.toml' }
    vi.mocked(api.getProject).mockRejectedValue(error)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)

    expect(await screen.findByText('Configuration error')).toBeInTheDocument()
    expect(screen.getByText('Invalid project configuration TOML')).toBeInTheDocument()
    expect(screen.getByText('/path/to/.openmcp/config.toml')).toBeInTheDocument()
  })
})
