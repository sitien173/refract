import { describe, expect, it, vi } from 'vitest'
import { clearCsrfToken, deleteConfigurationTarget, updateConfigurationTarget, updateMaxProjectReaders } from './api'

function response(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  }
}

describe('dashboard API mutation retry boundary', () => {
  it('submits reader capacity through the protected settings mutation with its revision', async () => {
    clearCsrfToken()
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(200, { csrf_token: 'settings-token' }))
      .mockResolvedValueOnce(response(200, { daemon: { max_project_readers: 4 } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateMaxProjectReaders(4, 'settings-rev')).resolves.toEqual({ daemon: { max_project_readers: 4 } })
    expect(fetchMock.mock.calls[1][0]).toBe('/dashboard/api/settings')
    expect(fetchMock.mock.calls[1][1].method).toBe('PUT')
    expect(fetchMock.mock.calls[1][1].headers['If-Match']).toBe('"settings-rev"')
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ max_project_readers: 4 })
  })

  it('does not retry an unstructured forbidden response', async () => {
    clearCsrfToken()
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(200, { csrf_token: 'token' }))
      .mockResolvedValueOnce(response(403, { error: 'Forbidden' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateConfigurationTarget('target', { backend: 'codex' }, 'rev')).rejects.toMatchObject({ status: 403 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('shares exactly one CSRF bootstrap request across concurrent mutations', async () => {
    clearCsrfToken()
    let bootstrapCalls = 0
    const fetchMock = vi.fn().mockImplementation(async (url) => {
      if (url === '/dashboard/api/bootstrap') {
        bootstrapCalls += 1
        await new Promise((resolve) => setTimeout(resolve, 10))
        return response(200, { csrf_token: 'shared-csrf-token' })
      }
      return response(200, { id: 'ok' })
    })
    vi.stubGlobal('fetch', fetchMock)

    const [res1, res2] = await Promise.all([
      updateConfigurationTarget('target-1', { backend: 'codex' }, 'rev 1'),
      deleteConfigurationTarget('target-2', 'rev 2'),
    ])

    expect(res1).toEqual({ id: 'ok' })
    expect(res2).toEqual({ id: 'ok' })
    expect(bootstrapCalls).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[0][0]).toBe('/dashboard/api/bootstrap')
    expect(fetchMock.mock.calls[1][1].headers['X-OpenMCP-CSRF']).toBe('shared-csrf-token')
    expect(fetchMock.mock.calls[2][1].headers['X-OpenMCP-CSRF']).toBe('shared-csrf-token')
  })
})
