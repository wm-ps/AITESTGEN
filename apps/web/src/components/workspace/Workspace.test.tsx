import { StrictMode } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

    await waitFor(() => expect(screen.getByText('Schedules', { selector: 'h1' })).toBeInTheDocument())
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
    expect(screen.getByText('Automate exploration and test runs on a cadence.')).toBeInTheDocument()
  })

  it('hides the Journeys/Scenarios shortcuts on Overview when exploration is disabled', async () => {
    stubEmptyOverview()
    render(
      <Workspace applicationId="app-1" activeTab="overview" onActiveTabChange={() => {}} discoveryEnabled={false} />,
    )

    await screen.findByText('Record and play')
    expect(screen.queryByText('View journeys')).toBeNull()
    expect(screen.queryByText('Review scenarios')).toBeNull()
    expect(screen.getByText('Automate test runs on a cadence.')).toBeInTheDocument()
  })

  // Cancel run sits beside "Running" in the Runs toolbar from the moment a
  // run is going.
  function stubRunsToolbar(state: { latest: Record<string, unknown> | null }) {
    const run = (status: string) => ({
      id: 'run-7',
      run_number: 7,
      name: '#7 - Full Suite Run',
      status,
      trigger: 'Manual run',
      pass_rate: null,
      health: { tier: 'healthy', headline: 'Healthy' },
      total_count: 3,
      passed_count: 1,
      failed_count: 0,
      timed_out_count: 0,
      errored_count: 0,
      blocked_count: 0,
      blocked_reason: null,
      environment_snapshot: 'staging',
      target_base_url_snapshot: 'https://x.example.com',
      created_at: '2026-09-01T00:00:00Z',
      started_at: null,
      completed_at: null,
      allure_report_available: false,
    })
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.endsWith('/test-runs/run-7/cancel')) {
        state.latest = run('cancelled')
        return { ok: true, status: 200, json: async () => ({ ...run('cancelled'), results: [] }) }
      }
      if (init?.method === 'POST' && url.endsWith('/test-runs')) {
        return { ok: true, status: 202, json: async () => ({ started: true }) }
      }
      const detail = url.match(/\/test-runs\/([^/?]+)$/)
      if (detail && state.latest) {
        return { ok: true, status: 200, json: async () => ({ ...state.latest, id: detail[1], results: [] }) }
      }
      if (url.includes('/test-suite-status')) {
        return { ok: true, status: 200, json: async () => ({ items: [], total: 1, page: 1, page_size: 1 }) }
      }
      if (url.includes('/test-runs')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: state.latest ? [state.latest] : [], next_cursor: null }),
        }
      }
      return { ok: true, status: 200, json: async () => ({ available: true }) }
    })
    vi.stubGlobal('fetch', fetchMock)
    return { fetchMock, run }
  }

  it('shows Cancel run beside Running and cancels the active run from there', async () => {
    const state: { latest: Record<string, unknown> | null } = { latest: null }
    const { fetchMock, run } = stubRunsToolbar(state)
    state.latest = run('running')

    render(<Workspace applicationId="app-1" activeTab="runs" onActiveTabChange={() => {}} />)

    const cancel = await screen.findByRole('button', { name: 'Cancel run' })
    expect(screen.getByRole('button', { name: 'Running' })).toBeInTheDocument()
    expect(cancel).toBeEnabled()

    fireEvent.click(cancel)
    const dialog = await screen.findByRole('dialog', { name: 'Cancel run' })
    expect(within(dialog).getByText('Cancel run #7?')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel run' }))

    // Straight back to "Run" — no waiting for the next poll.
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Running' })).toBeNull())
    expect(screen.queryByRole('button', { name: 'Cancel run' })).toBeNull()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/applications/app-1/test-runs/run-7/cancel'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('cancels the newly started run after a previous one finished (full lifecycle)', async () => {
    const state: { latest: Record<string, unknown> | null } = { latest: null }
    const { fetchMock, run } = stubRunsToolbar(state)
    state.latest = { ...run('cancelled'), id: 'run-6', run_number: 6 }

    render(<Workspace applicationId="app-1" activeTab="runs" onActiveTabChange={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Run' }))
    fireEvent.click(await screen.findByText('All test cases'))
    // Prepare creates the new run row a moment after the trigger.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/test-runs$/),
      expect.objectContaining({ method: 'POST' }),
    ))
    state.latest = run('running')

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel run' }))
    // The new run (#7), never the previous one (#6).
    const dialog = await screen.findByRole('dialog', { name: 'Cancel run' })
    expect(within(dialog).getByText('Cancel run #7?')).toBeInTheDocument()
  })

  // Regression: a browser whose poll never delivered the run left Cancel run
  // disabled for a whole run. It's always clickable and finds the run itself.
  it('finds and cancels the run on click even when the poll has not supplied it', async () => {
    const state: { latest: Record<string, unknown> | null } = { latest: null }
    const { fetchMock, run } = stubRunsToolbar(state)

    render(<Workspace applicationId="app-1" activeTab="runs" onActiveTabChange={() => {}} autoTriggerRun />)

    const cancel = await screen.findByRole('button', { name: 'Cancel run' }, { timeout: 4000 })
    expect(cancel).toBeEnabled()
    // The run row appears only now — after the last poll the toolbar saw.
    state.latest = run('running')
    fireEvent.click(cancel)

    const dialog = await screen.findByRole('dialog', { name: 'Cancel run' })
    expect(within(dialog).getByText('Cancel run #7?')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel run' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Running' })).toBeNull())
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/applications/app-1/test-runs/run-7/cancel'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('says the run is still starting when no run row exists yet', async () => {
    stubRunsToolbar({ latest: null })

    render(<Workspace applicationId="app-1" activeTab="runs" onActiveTabChange={() => {}} autoTriggerRun />)

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel run' }, { timeout: 4000 }))

    expect(
      await screen.findByText('The run is still starting — try again in a moment.', {}, { timeout: 8000 }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
  }, 15000)

  it('shows no Cancel run when nothing is running', async () => {
    const state: { latest: Record<string, unknown> | null } = { latest: null }
    const { run } = stubRunsToolbar(state)
    state.latest = run('completed')

    render(<Workspace applicationId="app-1" activeTab="runs" onActiveTabChange={() => {}} />)

    await screen.findByRole('button', { name: 'Run' })
    expect(screen.queryByRole('button', { name: 'Cancel run' })).toBeNull()
  })
})
