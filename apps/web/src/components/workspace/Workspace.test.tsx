import { StrictMode } from 'react'
import { render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Workspace } from './Workspace'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Workspace', () => {
  it('triggers exactly one test run on auto-trigger mount, even under StrictMode\'s double-invoked effect', async () => {
    let triggerCalls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST' && url.includes('/test-runs')) {
          triggerCalls += 1
          return { ok: true, status: 202, json: async () => ({ started: true }) }
        }
        if (url.includes('/test-runs')) {
          return { ok: true, status: 200, json: async () => ({ items: [], page: 1, page_size: 10, total: 0 }) }
        }
        return { ok: true, status: 200, json: async () => [] }
      }),
    )

    render(
      <StrictMode>
        <Workspace applicationId="app-1" initialTab="runs" autoTriggerRun />
      </StrictMode>,
    )

    await waitFor(() => expect(triggerCalls).toBeGreaterThan(0))
    // Give any erroneous second StrictMode-driven call a chance to land
    // before asserting it didn't.
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(triggerCalls).toBe(1)
  })
})
