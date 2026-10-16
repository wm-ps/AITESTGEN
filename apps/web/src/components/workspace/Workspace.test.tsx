import { StrictMode } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
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
        <Workspace applicationId="app-1" activeTab="runs" onActiveTabChange={() => {}} autoTriggerRun />
      </StrictMode>,
    )

    await waitFor(() => expect(triggerCalls).toBeGreaterThan(0))
    // Give any erroneous second StrictMode-driven call a chance to land
    // before asserting it didn't.
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(triggerCalls).toBe(1)
  })

  it('renders the Schedules tab and fetches from the schedules endpoint', async () => {
    let hitSchedules = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/schedules')) {
          hitSchedules = true
          return { ok: true, status: 200, json: async () => [] }
        }
        return { ok: true, status: 200, json: async () => [] }
      }),
    )

    render(<Workspace applicationId="app-1" activeTab="schedules" onActiveTabChange={() => {}} />)

    await waitFor(() => expect(screen.getByText('Schedules and CI', { selector: 'h1' })).toBeInTheDocument())
    await waitFor(() => expect(hitSchedules).toBe(true))
  })

  // No test run yet, so the Overview tab renders just the empty state and the
  // quick-action cards — the part that differs with discovery on/off.
  function stubEmptyOverview() {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/overview')) {
          return { ok: true, status: 200, json: async () => ({ latest_run: null }) }
        }
        return { ok: true, status: 200, json: async () => [] }
      }),
    )
  }

  it('shows the Journeys/Scenarios shortcuts on Overview by default', async () => {
    stubEmptyOverview()
    render(<Workspace applicationId="app-1" activeTab="overview" onActiveTabChange={() => {}} />)

    await screen.findByText('View journeys')
    expect(screen.getByText('Review scenarios')).toBeInTheDocument()
    expect(screen.getByText('Automate discovery and suite runs on a cadence.')).toBeInTheDocument()
  })

  it('hides the Journeys/Scenarios shortcuts on Overview when discovery is disabled', async () => {
    stubEmptyOverview()
    render(
      <Workspace applicationId="app-1" activeTab="overview" onActiveTabChange={() => {}} discoveryEnabled={false} />,
    )

    await screen.findByText('Record and play')
    expect(screen.queryByText('View journeys')).toBeNull()
    expect(screen.queryByText('Review scenarios')).toBeNull()
    expect(screen.getByText('Automate suite runs on a cadence.')).toBeInTheDocument()
  })
})
