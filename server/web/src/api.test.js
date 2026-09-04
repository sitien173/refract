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
})
