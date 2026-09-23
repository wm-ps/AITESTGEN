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
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
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

  it('lists saved credentials with a masked secret, and reveals it on click', async () => {
    stubFetch()
    render(<Settings user={ADMIN} onCancel={vi.fn()} />)

    await screen.findByText('Checkout App')
    expect(screen.getByText('qa-account')).toBeTruthy()
    expect(screen.getByText('••••••••')).toBeTruthy()

    fireEvent.click(screen.getByTitle('Reveal'))
    expect(await screen.findByText('super-secret')).toBeTruthy()
  })
})
