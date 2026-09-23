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
})
