import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Home } from './Home'

const USER = { name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' as const }

const APP = {
  id: 'app-1',
  name: 'Checkout App',
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
  last_test_run_status: null,
  last_test_run_created_at: null,
  last_test_run_pass_rate: null,
  test_run_count: 0,
  recent_pass_rates: [],
  suite_count: 1,
  test_case_count: 5,
  suites_generating_count: 0,
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => [APP] })),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('Home view toggle', () => {
  it('defaults to grid view and lets the user switch to list view', async () => {
    stubFetch()
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)
    await screen.findByText('Checkout App')

    expect(screen.getByRole('button', { name: 'Grid view' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'List view' }).getAttribute('aria-pressed')).toBe('false')

    fireEvent.click(screen.getByRole('button', { name: 'List view' }))

    expect(screen.getByRole('button', { name: 'List view' }).getAttribute('aria-pressed')).toBe('true')
    expect(localStorage.getItem('aitg-home-view')).toBe('list')
  })

  it('restores the previously chosen view from localStorage', async () => {
    localStorage.setItem('aitg-home-view', 'list')
    stubFetch()
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)
    await screen.findByText('Checkout App')

    expect(screen.getByRole('button', { name: 'List view' }).getAttribute('aria-pressed')).toBe('true')
  })
})
