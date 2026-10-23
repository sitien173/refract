import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DashboardApiError } from '../api'
import { useConfigEditor } from './useConfigEditor'

describe('useConfigEditor submit lifecycle', () => {
  it('guards immediate duplicate submits and close until success callbacks complete', async () => {
    let resolve
    const save = vi.fn(() => new Promise((done) => { resolve = done }))
    const onClose = vi.fn()
    const onSaved = vi.fn()
    const onAnnounce = vi.fn()
    const { result } = renderHook(() => useConfigEditor({
      revision: 'original', onClose, onSaved, onAnnounce,
    }))
    result.current.isDirtyRef.current = true
    const options = {
      save, entity: 'target', savingMessage: 'Saving configuration…',
      successMessage: (saved) => `Target "${saved.target.id}" saved and active.`,
    }
    let pending
    act(() => {
      pending = result.current.submit(options)
      result.current.submit(options)
      result.current.handleClose()
    })
    expect(save).toHaveBeenCalledExactlyOnceWith('original')
    expect(result.current.saveStatus).toBe('saving')
    expect(onClose).not.toHaveBeenCalled()
    expect(onSaved).not.toHaveBeenCalled()

    const saved = { target: { id: 'demo' } }
    await act(async () => {
      resolve(saved)
      await pending
    })
    expect(onSaved).toHaveBeenCalledExactlyOnceWith(saved)
    expect(onClose).toHaveBeenCalledOnce()
    expect(onAnnounce.mock.calls).toEqual([
      ['Saving configuration…'], ['Target "demo" saved and active.'],
    ])
    expect(result.current.isDirtyRef.current).toBe(false)
    expect(result.current.inFlightRef.current).toBe(false)
    expect(result.current.saveStatus).toBe('')
  })

  it('preserves dirty state on save failure and releases the guard for retry', async () => {
    const save = vi.fn().mockRejectedValueOnce(new DashboardApiError('Rejected', 400, { error: 'Invalid target.' }))
      .mockResolvedValueOnce({ target: { id: 'demo' } })
    const onClose = vi.fn()
    const onSaved = vi.fn()
    const { result } = renderHook(() => useConfigEditor({ revision: 'original', onClose, onSaved }))
    result.current.isDirtyRef.current = true
    const options = { save, entity: 'target', successMessage: () => 'Saved.' }
    await act(async () => { await result.current.submit(options) })
    expect(result.current.error).toBe('Invalid target.')
    expect(result.current.isDirtyRef.current).toBe(true)
    expect(result.current.inFlightRef.current).toBe(false)
    expect(onClose).not.toHaveBeenCalled()
    expect(onSaved).not.toHaveBeenCalled()

    await act(async () => { await result.current.submit(options) })
    expect(save).toHaveBeenCalledTimes(2)
    expect(result.current.error).toBe(null)
    expect(onSaved).toHaveBeenCalledOnce()
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('requires successful reload after conflict and blocks save while reloading', async () => {
    const save = vi.fn().mockRejectedValueOnce(new DashboardApiError('Conflict', 409, { current: 'newer' }))
      .mockResolvedValueOnce({ profile: { id: 'demo' } })
    const onClose = vi.fn()
    const { result } = renderHook(() => useConfigEditor({ revision: 'original', onClose }))
    result.current.isDirtyRef.current = true
    const options = { save, entity: 'profile', successMessage: () => 'Saved.' }
    await act(async () => { await result.current.submit(options) })
    await act(async () => { await result.current.submit(options) })
    expect(save).toHaveBeenCalledTimes(1)
    expect(result.current.currentRevision).toBe('original')
    expect(result.current.isDirtyRef.current).toBe(true)
    expect(onClose).not.toHaveBeenCalled()

    const apply = vi.fn()
    const reloadOptions = { select: (payload) => payload.profile, apply, mode: 'edit', entity: 'Profile' }
    await act(async () => {
      await result.current.reload({ ...reloadOptions, load: async () => ({ revision: 'newer' }) })
    })
    expect(result.current.conflictData).not.toBe(null)
    expect(result.current.currentRevision).toBe('original')
    expect(apply).not.toHaveBeenCalled()

    let resolve
    let pending
    act(() => {
      pending = result.current.reload({
        ...reloadOptions, load: () => new Promise((done) => { resolve = done }),
      })
      result.current.submit(options)
    })
    expect(save).toHaveBeenCalledTimes(1)
    expect(result.current.saveStatus).toBe('reloading')
    await act(async () => {
      resolve({ revision: 'newer', profile: { id: 'demo' } })
      await pending
    })
    expect(apply).toHaveBeenCalledExactlyOnceWith({ id: 'demo' })
    expect(result.current.conflictData).toBe(null)
    expect(result.current.isDirtyRef.current).toBe(false)
    await act(async () => { await result.current.submit(options) })
    expect(save).toHaveBeenLastCalledWith('newer')
    expect(onClose).toHaveBeenCalledOnce()
  })
})
