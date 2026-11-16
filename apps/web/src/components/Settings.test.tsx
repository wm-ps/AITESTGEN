import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

// Settings opens on the hub of cards; each section is one click away.
async function openSection(title: string) {
  render(<Settings user={ADMIN} onCancel={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: `Configure ${title}` }))
}

describe('Settings', () => {
  it('shows Access denied for a non-admin', async () => {
    render(<Settings user={MEMBER} onCancel={vi.fn()} />)
    expect(await screen.findByText('Access denied')).toBeTruthy()
  })

  it('shows approved domains as chips with no edit option', async () => {
    stubFetch()
    await openSection('Saved credentials')

    await screen.findByText('shop.example.com')
    expect(screen.getByText('spare.example.com')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull()
  })

  it('refuses to remove a domain an application uses, and says which applications', async () => {
    stubFetch()
    await openSection('Saved credentials')
    await screen.findByText('shop.example.com')

    fireEvent.click(screen.getByRole('button', { name: 'Remove shop.example.com' }))

    const alert = await screen.findByText(/is used by Shop Frontend/)
    expect(alert.textContent).toContain('Delete those applications first')
    expect(screen.getByText('shop.example.com')).toBeTruthy()
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  })

  it('removes a domain no application uses', async () => {
    stubFetch()
    await openSection('Saved credentials')
    await screen.findByText('spare.example.com')

    fireEvent.click(screen.getByRole('button', { name: 'Remove spare.example.com' }))

    await vi.waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'DELETE')
      expect(String(call?.[0])).toMatch(/\/domains\/dom-2$/)
    })
  })

  it('adds an approved domain on Enter', async () => {
    stubFetch()
    await openSection('Saved credentials')
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

  it('lists saved credentials but leaves adding them to each application', async () => {
    stubFetch()
    await openSection('Saved credentials')
    expect(await screen.findByText('Checkout App')).toBeTruthy()
    expect(screen.queryByText('Add credentials')).toBeNull()
    expect(screen.getByText(/open its Application settings/)).toBeTruthy()
  })

  it('lists saved credentials with a masked secret, and reveals it on click', async () => {
    stubFetch()
    await openSection('Saved credentials')

    await screen.findByText('Checkout App')
    expect(screen.getByText('qa-account')).toBeTruthy()
    expect(screen.getByText('••••••••')).toBeTruthy()

    fireEvent.click(screen.getByTitle('Reveal'))
    expect(await screen.findByText('super-secret')).toBeTruthy()
  })

  it('turns sign-in off for an app with no login', async () => {
    stubFetch()
    await openSection('Saved credentials')
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

  it('opens on a hub with one card per section', async () => {
    stubFetch()
    render(<Settings user={ADMIN} onCancel={vi.fn()} />)
    for (const title of ['Saved credentials', 'Data retention'])
      expect(await screen.findByRole('button', { name: `Configure ${title}` })).toBeTruthy()
    // An application's own settings live on its Settings tab, not here.
    for (const title of ['Explorer limits', 'Test case generation'])
      expect(screen.queryByRole('button', { name: `Configure ${title}` })).toBeNull()
  })

  it('discards unsaved changes and goes back to the hub', async () => {
    stubFetch()
    await openSection('Data retention')
    const cleanUp = (await screen.findByLabelText(/Clean up/)) as HTMLSelectElement
    fireEvent.change(cleanUp, { target: { value: '1_day' } })
    fireEvent.click(screen.getByRole('button', { name: 'Discard Changes' }))
    expect((screen.getByLabelText(/Clean up/) as HTMLSelectElement).value).toBe('1_week')
    fireEvent.click(screen.getByText('Back to Settings'))
    expect(await screen.findByRole('button', { name: 'Configure Data retention' })).toBeTruthy()
  })

  it('saves the data retention period', async () => {
    stubFetch()
    await openSection('Data retention')
    fireEvent.change(await screen.findByLabelText(/Clean up/), { target: { value: '1_month' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Configuration' }))
    await waitFor(() => {
      const patch = vi.mocked(fetch).mock.calls.find(([url, init]) => String(url).endsWith('/settings') && init?.method === 'PATCH')
      expect(JSON.parse(String(patch![1]!.body)).delete_project_after).toBe('1_month')
    })
  })
})
