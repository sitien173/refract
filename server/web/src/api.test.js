import { describe, expect, it, vi } from 'vitest'
import { clearCsrfToken, deleteContextInstruction, updateContextInstruction } from './api'

function response(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  }
}

describe('dashboard API mutation retry boundary', () => {
  it('always sends an expected current value in DELETE bodies', async () => {
    clearCsrfToken()
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(200, { csrf_token: 'token' }))
      .mockResolvedValueOnce(response(200, { instruction: '' }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteContextInstruction('project', 'consult')

    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ expected_current: '' })
  })

  it('does not retry an unstructured forbidden response', async () => {
    clearCsrfToken()
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(200, { csrf_token: 'token' }))
      .mockResolvedValueOnce(response(403, { error: 'Forbidden' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateContextInstruction('project', 'consult', 'draft', '')).rejects.toMatchObject({ status: 403 })
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
      return response(200, { instruction: 'ok' })
    })
    vi.stubGlobal('fetch', fetchMock)

    const [res1, res2] = await Promise.all([
      updateContextInstruction('proj-1', 'consult', 'instruction 1', 'old 1'),
      deleteContextInstruction('proj-1', 'implement', 'old 2'),
    ])

    expect(res1).toEqual({ instruction: 'ok' })
    expect(res2).toEqual({ instruction: 'ok' })
    expect(bootstrapCalls).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[0][0]).toBe('/dashboard/api/bootstrap')
    expect(fetchMock.mock.calls[1][1].headers['X-OpenMCP-CSRF']).toBe('shared-csrf-token')
    expect(fetchMock.mock.calls[2][1].headers['X-OpenMCP-CSRF']).toBe('shared-csrf-token')
  })
})
