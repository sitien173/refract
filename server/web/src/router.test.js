import { describe, it, expect } from 'vitest'
import { parseHash } from './router.js'

describe('Hash router', () => {
  it('parses empty hash as jobs route', () => {
    expect(parseHash('')).toEqual({ route: 'jobs', params: {} })
    expect(parseHash('#/')).toEqual({ route: 'jobs', params: {} })
  })

  it('parses #/jobs and #/jobs/:id', () => {
    expect(parseHash('#/jobs')).toEqual({ route: 'jobs', params: {} })
    expect(parseHash('#/jobs/job-123')).toEqual({
      route: 'jobs',
      params: { id: 'job-123' },
    })
  })

  it('parses #/projects and #/projects/:id', () => {
    expect(parseHash('#/projects')).toEqual({ route: 'projects', params: {} })
    expect(parseHash('#/projects/proj-abc')).toEqual({
      route: 'projects',
      params: { id: 'proj-abc' },
    })
  })

  it('parses #/targets, #/diagnostics, #/runtime', () => {
    expect(parseHash('#/targets')).toEqual({ route: 'targets', params: {} })
    expect(parseHash('#/diagnostics')).toEqual({ route: 'diagnostics', params: {} })
    expect(parseHash('#/runtime')).toEqual({ route: 'runtime', params: {} })
  })
})
