import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDiscoveryProgress } from './useDiscoveryProgress'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useDiscoveryProgress', () => {
  it('returns the initial values before any poll resolves', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          discovery_status: 'running',
          discovery_stage: 'initializing',
          discovery_failure_reason: null,
        }),
      }),
    )

    const { result } = renderHook(() =>
      useDiscoveryProgress('app-1', 'running', 'initializing', null, false),
    )

    expect(result.current).toEqual({ status: 'running', stage: 'initializing', failureReason: null })
    // Let the in-flight poll settle before the test ends — otherwise its
    // state update lands after teardown and logs a spurious act() warning.
    await waitFor(() => expect(result.current.status).toBe('running'))
  })

  it('updates status/stage/failureReason from a poll response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          discovery_status: 'failed',
          discovery_stage: null,
          discovery_failure_reason: 'session_expired',
        }),
      }),
    )

    const { result } = renderHook(() =>
      useDiscoveryProgress('app-1', 'running', 'discovering', null, false),
    )

    await waitFor(() => {
      expect(result.current.status).toBe('failed')
    })
    expect(result.current.stage).toBeNull()
    expect(result.current.failureReason).toBe('session_expired')
  })

  it('does not poll once hasJourneys is true', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        discovery_status: 'running',
        discovery_stage: 'discovering',
        discovery_failure_reason: null,
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useDiscoveryProgress('app-1', 'running', 'initializing', null, true))

    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not poll once the initial status is already failed', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useDiscoveryProgress('app-1', 'failed', null, 'session_expired', false))

    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
