import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Settings } from './Settings'

const ADMIN = { name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' as const }
const MEMBER = { name: 'Bob Member', email: 'bob@example.com', role: 'member' as const }

const SETTINGS_BODY = {
  max_pages: 60,
  max_discovery_duration_minutes: 15,
  navigation_timeout_seconds: 30,
  interaction_level: 'normal',
  max_journeys: 12,
  max_scenarios_per_journey: null,
  max_test_cases_per_application: null,
  delete_project_after: '1_week',
  max_heal_attempts: 3,
}

const CREDENTIAL_ENTRY = {
  application_id: 'app-1',
  application_name: 'Checkout App',
  environment: 'staging',
  username: 'qa-account',
  has_password: true,
  requires_login: true,
}

const DOMAIN_IN_USE = {
  id: 'dom-1',
  host: 'shop.example.com',
  created_by: 'Ada Lovelace',
  applications: [{ id: 'app-9', name: 'Shop Frontend' }],
}

const DOMAIN_UNUSED = { id: 'dom-2', host: 'spare.example.com', created_by: 'Ada Lovelace', applications: [] }

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/domains')) return { ok: true, status: 200, json: async () => [DOMAIN_IN_USE, DOMAIN_UNUSED] }
      if (url.endsWith('/settings')) return { ok: true, status: 200, json: async () => SETTINGS_BODY }
      // CredentialsPanel hides itself entirely when `apps` is empty (nothing
      // to point an "Add credentials" form at) — must be non-empty for the
      // credentials table (from `/credentials`, below) to render at all. A
      // deliberately different name than CREDENTIAL_ENTRY's — this app just
      // populates the separate "Add credentials" dropdown, and a shared name
      // would make `getByText('Checkout App')` ambiguous (table row + option).
      if (url.endsWith('/home'))
        return {
          ok: true,
          status: 200,
          json: async () => [{ id: 'app-2', name: 'Marketing Site', environment: 'staging' }],
        }
      if (url.endsWith('/credentials')) return { ok: true, status: 200, json: async () => [CREDENTIAL_ENTRY] }
      if (url.endsWith('/credentials/app-1/reveal')) return { ok: true, status: 200, json: async () => ({ password: 'super-secret' }) }
      if (url.endsWith('/credentials/app-1/verify')) return { ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) }
      return { ok: true, status: 200, json: async () => ({}) }
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Settings', () => {
  it('shows Access denied for a non-admin', async () => {
    render(<Settings user={MEMBER} onCancel={vi.fn()} />)
    expect(await screen.findByText('Access denied')).toBeTruthy()
  })

  it('shows approved domains as chips with no edit option', async () => {
    stubFetch()
    render(<Settings user={ADMIN} onCancel={vi.fn()} />)

    await screen.findByText('shop.example.com')
    expect(screen.getByText('spare.example.com')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull()
  })

  it('refuses to remove a domain an application uses, and says which applications', async () => {
    stubFetch()
    render(<Settings user={ADMIN} onCancel={vi.fn()} />)
    await screen.findByText('shop.example.com')

    fireEvent.click(screen.getByRole('button', { name: 'Remove shop.example.com' }))

    const alert = await screen.findByText(/is used by Shop Frontend/)
    expect(alert.textContent).toContain('Delete those applications first')
    expect(screen.getByText('shop.example.com')).toBeTruthy()
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  })

  it('removes a domain no application uses', async () => {
    stubFetch()
    render(<Settings user={ADMIN} onCancel={vi.fn()} />)
    await screen.findByText('spare.example.com')

    fireEvent.click(screen.getByRole('button', { name: 'Remove spare.example.com' }))

    await vi.waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'DELETE')
      expect(String(call?.[0])).toMatch(/\/domains\/dom-2$/)
    })
  })

  it('adds an approved domain on Enter', async () => {
    stubFetch()
    render(<Settings user={ADMIN} onCancel={vi.fn()} />)
    await screen.findByText('shop.example.com')

    const input = screen.getByLabelText('Add a domain')
    fireEvent.change(input, { target: { value: 'example.org' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    const fetchMock = vi.mocked(fetch)
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/domains') && init?.method === 'POST')
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ host: 'example.org' })
    })
  })

  it('lists saved credentials with a masked secret, and reveals it on click', async () => {
    stubFetch()
    render(<Settings user={ADMIN} onCancel={vi.fn()} />)

    await screen.findByText('Checkout App')
    expect(screen.getByText('qa-account')).toBeTruthy()
    expect(screen.getByText('••••••••')).toBeTruthy()

    fireEvent.click(screen.getByTitle('Reveal'))
    expect(await screen.findByText('super-secret')).toBeTruthy()
  })

  it('turns sign-in off for an app with no login', async () => {
    stubFetch()
    render(<Settings user={ADMIN} onCancel={vi.fn()} />)
    const toggle = await screen.findByRole('switch', { name: 'Checkout App requires sign-in' })
    expect(toggle.getAttribute('aria-checked')).toBe('true')

    fireEvent.click(toggle)

    const fetchMock = vi.mocked(fetch)
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/applications/app-1/requires-login'))).toBe(true),
    )
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/applications/app-1/requires-login'))!
    expect(call[1]?.method).toBe('PATCH')
    expect(JSON.parse(String(call[1]?.body))).toEqual({ requires_login: false })
  })
})
