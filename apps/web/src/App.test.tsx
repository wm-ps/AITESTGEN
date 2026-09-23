import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function mockFetchOnce(body: unknown, ok: boolean, status: number) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => body,
  })
}

afterEach(() => {
  // Explicit, ordered before unstubbing fetch: unmounting while the mock is
  // still in place lets any in-flight request from a still-mounted
  // component (a poll interval, a pending promise) resolve/settle against
  // it and be torn down cleanly, rather than firing later against a
  // restored/undefined `fetch` and leaking a stray `window` event (e.g.
  // `auth:expired`) into whichever test happens to be running next.
  cleanup()
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('renders Sign in when there is no session, with the default tab title/favicon', async () => {
    vi.stubGlobal('fetch', mockFetchOnce({ detail: 'not signed in' }, false, 401))
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeTruthy()
    })
    expect(document.title).toBe('Vantage')
    expect(document.querySelector('link[rel="icon"]')?.getAttribute('href')).toBe('/favicon.png')
  })

  it('renders Applications with the sidebar shell and avatar menu when signed in, with the default tab title/favicon', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).endsWith('/home')) return { ok: true, status: 200, json: async () => [] }
        return {
          ok: true,
          status: 200,
          json: async () => ({ name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' }),
        }
      }),
    )
    render(<App />)

    // The global Overview dashboard is the default landing page after sign-in
    // now — navigate into Applications (sidebar) for this test's own concerns
    // (the empty-state copy and the avatar menu), same as a real user would.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Overview' })).toBeTruthy()
    })
    fireEvent.click(screen.getByText('Applications'))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Applications' })).toBeTruthy()
    })
    expect(screen.getByText('Add your first application')).toBeTruthy()
    expect(document.title).toBe('Vantage')
    expect(document.querySelector('link[rel="icon"]')?.getAttribute('href')).toBe('/favicon.png')

    fireEvent.click(screen.getByRole('button', { name: 'AL' }))

    expect(screen.getByText('ada@example.com')).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Log out' })).toBeTruthy()
  })

  it('connects an application and lands on its Journeys tab, with the Application section in the sidebar', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url)
      if (path.endsWith('/auth/me')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' }),
        }
      }
      if (path.endsWith('/home')) return { ok: true, status: 200, json: async () => [] }
      if (path.endsWith('/applications') && init?.method === 'POST') {
        return {
          ok: true,
          status: 201,
          json: async () => ({
            id: 'app-1',
            name: 'My App',
            url: 'https://staging.example.com',
            environment: 'staging',
            auth_method: 'standard_login',
            created_at: new Date(0).toISOString(),
            discovery_run_id: 'run-1',
            discovery_status: 'running',
            discovery_stage: 'initializing',
          }),
        }
      }
      return { ok: true, status: 200, json: async () => [] }
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    // Global Overview is the default landing page after sign-in — navigate
    // into Applications first, same as a real user would.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Overview' })).toBeTruthy()
    })
    fireEvent.click(screen.getByText('Applications'))

    await waitFor(() => {
      expect(screen.getByText('Add your first application')).toBeTruthy()
    })
    // Both the topbar CTA and the empty-state's own button are named "Add
    // application" and call the same handler — either works.
    fireEvent.click(screen.getAllByRole('button', { name: 'Add application' })[0])

    fireEvent.change(screen.getByLabelText('Application name'), { target: { value: 'My App' } })
    fireEvent.change(screen.getByLabelText('Deployed URL'), {
      target: { value: 'https://staging.example.com' },
    })
    fireEvent.change(screen.getByLabelText('Environment'), { target: { value: 'staging' } })
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'qa-account' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'qa-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start discovery' }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Journeys' })).toBeTruthy()
    })
    // The sidebar's Application section names the connected app and shows
    // the full per-app tab set, not just Journeys — "My App" legitimately
    // appears twice (sidebar + the page's own AppIdentityLine breadcrumb).
    expect(screen.getAllByText('My App').length).toBeGreaterThan(0)
    expect(screen.getByText('Scenarios')).toBeTruthy()
    expect(screen.getByText('Record and play')).toBeTruthy()

    // Tab title/favicon are static platform branding — unaffected by the Application.
    expect(document.title).toBe('Vantage')
    expect(document.querySelector('link[rel="icon"]')?.getAttribute('href')).toBe('/favicon.png')
  })

  it('resumes an existing application from its Home card, landing on the app view', async () => {
    const APPLICATION = {
      id: 'app-1',
      name: 'My App',
      url: 'https://staging.example.com',
      login_url: null,
      environment: 'staging',
      auth_method: 'standard_login',
      created_at: new Date(0).toISOString(),
      discovery_run_id: 'run-1',
      discovery_status: 'complete',
      discovery_stage: 'analyzed',
      discovery_failure_reason: null,
      journey_count: 2,
      scenario_count: 3,
      scenario_journeys_covered: 2,
      suite_count: 0,
      test_case_count: 0,
      suites_generating_count: 0,
      live_exploration_generating: false,
      last_test_run_status: null,
      last_test_run_created_at: null,
      last_test_run_pass_rate: null,
      last_test_run_health: { tier: 'needs_attention', headline: 'No tests have run yet' },
      test_run_count: 0,
      recent_pass_rates: [],
    }
    const fetchMock = vi.fn((url: string) => {
      const path = String(url)
      if (path.endsWith('/auth/me')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' }),
        })
      }
      if (path.endsWith('/home')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => [APPLICATION] })
      }
      if (path.endsWith('/scenarios')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => [{}, {}, {}] })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => [] })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    // Global Overview is the default landing page after sign-in — navigate
    // into Applications first, same as a real user would.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Overview' })).toBeTruthy()
    })
    fireEvent.click(screen.getByText('Applications'))

    await waitFor(() => {
      expect(screen.getByText('My App')).toBeTruthy()
    })
    fireEvent.click(screen.getByText('My App'))

    // Two Scenarios already exist for two of two Journeys covered — resume
    // lands on the Scenarios tab (the same "furthest reached" logic the old
    // Stepper-driven resume used, just landing on a tab key now).
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Scenarios' })).toBeTruthy()
    })
  })
})
