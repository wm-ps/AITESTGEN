import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Home } from './Home'

const USER = { name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' as const }

const BASE_APP = {
  url: 'https://example.com',
  login_url: null,
  environment: 'staging',
  auth_method: 'standard_login',
  created_at: new Date().toISOString(),
  discovery_run_id: 'run-1',
  discovery_status: 'complete',
  discovery_stage: 'analyzed',
  discovery_failure_reason: null,
  journey_count: 3,
  scenario_count: 3,
  scenario_journeys_covered: 3,
  last_test_run_status: 'completed',
  last_test_run_created_at: new Date().toISOString(),
  test_run_count: 1,
  recent_pass_rates: [0.95],
  suite_count: 1,
  test_case_count: 5,
  suites_generating_count: 0,
  live_exploration_generating: false,
  journeys_with_generation_error: 0,
  failed_journey_names: [] as string[],
}

const HEALTHY_APP = {
  ...BASE_APP,
  id: 'app-1',
  name: 'Checkout App',
  last_test_run_pass_rate: 0.95,
  last_test_run_health: { tier: 'healthy', headline: 'Healthy' },
}

function stubFetch(apps: unknown[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => apps })),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('Home applications table', () => {
  it('lists applications as table rows with their status', async () => {
    stubFetch([HEALTHY_APP])
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)

    await screen.findByText('Checkout App')
    expect(screen.getByText('https://example.com')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Application' })).toBeInTheDocument()
  })

  it('shows the empty state with no applications', async () => {
    stubFetch([])
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)

    await screen.findByText('Add your first application')
  })

  it('`[FIXED generation-stuck]` does not read a permanently-failed Journey as still generating', async () => {
    // 2 journeys total; 1 has a real Scenario, the other permanently failed
    // (generation_error set, retries exhausted) — never gets one. Before the
    // fix, `scenario_journeys_covered` (1) < `journey_count` (2) forever,
    // showing "Generating scenarios" with no way out. Both are now "done".
    stubFetch([
      {
        ...BASE_APP,
        id: 'app-stuck',
        name: 'Stuck App',
        journey_count: 2,
        scenario_count: 1,
        scenario_journeys_covered: 1,
        journeys_with_generation_error: 1,
        failed_journey_names: ['Broken Journey'],
        last_test_run_status: null,
        last_test_run_created_at: null,
        last_test_run_pass_rate: null,
        last_test_run_health: { tier: 'needs_attention', headline: 'No tests have run yet' },
        test_run_count: 0,
        recent_pass_rates: [],
        suite_count: 0,
        test_case_count: 0,
      },
    ])
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)

    await screen.findByText('Stuck App')
    expect(screen.getByText('Scenarios generated')).toBeInTheDocument()
    expect(screen.queryByText('Generating scenarios')).toBeNull()
  })

  it('`[ADDED generation-stuck notification]` shows a toast the poll a Journey is newly seen as failed, not on the first load', async () => {
    vi.useFakeTimers()
    let call = 0
    const firstResponse = [{ ...BASE_APP, id: 'app-1', name: 'Checkout App' }]
    const secondResponse = [
      { ...BASE_APP, id: 'app-1', name: 'Checkout App', journeys_with_generation_error: 1, failed_journey_names: ['Broken Journey'] },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        call += 1
        return { ok: true, status: 200, json: async () => (call === 1 ? firstResponse : secondResponse) }
      }),
    )
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)

    await vi.waitFor(() => expect(screen.getByText('Checkout App')).toBeInTheDocument())
    expect(screen.queryByText(/Scenario generation failed/)).toBeNull()

    await vi.advanceTimersByTimeAsync(15000)
    await vi.waitFor(() =>
      expect(
        screen.getByText('Scenario generation failed for "Broken Journey" in Checkout App — continuing with the remaining journeys.'),
      ).toBeInTheDocument(),
    )

    vi.useRealTimers()
  })
})
