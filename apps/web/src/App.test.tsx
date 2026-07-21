import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('renders Sign in when there is no session, with the default tab title/favicon', async () => {
    vi.stubGlobal('fetch', mockFetchOnce({ detail: 'not signed in' }, false, 401))
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy()
    })
    expect(document.title).toBe('AITestGen')
    expect(document.querySelector('link[rel="icon"]')?.getAttribute('href')).toBe('/favicon.svg')
  })

  it('renders Home with the top bar and avatar menu when signed in, with the default tab title/favicon', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchOnce({ name: 'Ada Lovelace', email: 'ada@example.com' }, true, 200),
    )
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Welcome back, Ada' })).toBeTruthy()
    })
    expect(screen.getByText('Start a New Project')).toBeTruthy()
    expect(document.title).toBe('AITestGen')
    expect(document.querySelector('link[rel="icon"]')?.getAttribute('href')).toBe('/favicon.svg')

    fireEvent.click(screen.getByRole('button', { name: 'AL' }))

    expect(screen.getByText('ada@example.com')).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Log out' })).toBeTruthy()
  })

  it('shows the Application-name breadcrumb and a Running status pill on Discover Journeys after connecting an Application', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ name: 'Ada Lovelace', email: 'ada@example.com' }),
      })
      .mockResolvedValueOnce({
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
      })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Start a New Project')).toBeTruthy()
    })
    fireEvent.click(screen.getByText('Start a New Project'))

    fireEvent.change(screen.getByLabelText('Application name'), { target: { value: 'My App' } })
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://staging.example.com' },
    })
    fireEvent.change(screen.getByLabelText('Environment'), { target: { value: 'staging' } })
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'qa-account' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'qa-password' } })
    fireEvent.click(screen.getByRole('button', { name: /Connect Application/ }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Discover Journeys' })).toBeTruthy()
    })
    expect(screen.getByText('My App')).toBeTruthy()
    expect(screen.getByText('staging')).toBeTruthy()
    expect(screen.getByText('Running')).toBeTruthy()

    // Tab title/favicon are static platform branding — unaffected by the Application.
    expect(document.title).toBe('AITestGen')
    expect(document.querySelector('link[rel="icon"]')?.getAttribute('href')).toBe('/favicon.svg')
  })
})
