import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EnvironmentRead, Role } from '../../api'
import { EnvironmentsProvider, type EnvironmentsValue } from '../environments/EnvironmentsContext'
import { PermissionsProvider } from '../../PermissionsContext'
import { AppSettingsTab } from './AppSettingsTab'

const DEFAULT_ENV: EnvironmentRead = {
  id: null,
  name: 'production',
  url: 'https://prod.example.com',
  login_url: 'https://prod.example.com/signin',
  is_default: true,
  auth_method: 'standard_login',
  username: 'qa-account',
}
const UAT: EnvironmentRead = {
  id: 'env-1',
  name: 'UAT',
  url: 'https://uat.example.com',
  login_url: null,
  is_default: false,
  auth_method: 'standard_login',
  username: 'uat-account',
}

function renderTab({
  role = 'member',
  environments = [DEFAULT_ENV, UAT],
  canAdd = true,
  card = 'Environment Settings',
}: { role?: Role; environments?: EnvironmentRead[]; canAdd?: boolean; card?: string | null } = {}) {
  const value: EnvironmentsValue = {
    environments,
    refresh: vi.fn(async () => {}),
    requestAdd: vi.fn(),
    canAdd,
  }
  render(
    <PermissionsProvider value={role}>
      <EnvironmentsProvider value={value}>
        <AppSettingsTab applicationId="app-1" />
      </EnvironmentsProvider>
    </PermissionsProvider>,
  )
  // The tab opens on its card hub; each section is behind its card.
  if (card) fireEvent.click(screen.getByRole('button', { name: `Configure ${card}` }))
  return value
}

function stubFetch(handler: (path: string, method: string) => { status?: number; body?: unknown }) {
  const calls: { path: string; method: string }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: { method?: string }) => {
      const path = new URL(url).pathname
      const method = init?.method ?? 'GET'
      calls.push({ path, method })
      const reply = handler(path, method)
      const status = reply.status ?? 200
      return { ok: status < 400, status, json: async () => reply.body ?? {} }
    }),
  )
  return calls
}

const EXPLORER_LIMITS = {
  question_wait_minutes: 30,
  mission_time_limit_minutes: 75,
  run_time_limit_minutes: null,
  first_look_time_limit_minutes: 120,
  hidden_screen_search_minutes: 25,
  ai_budget_usd: null,
  first_look_max_screens: 150,
  max_missions: 15,
  steps_per_mission: 20,
  steps_per_scenario: 20,
  steps_per_journey: 40,
  max_scenarios: 150,
  proof_replays: 1,
  same_screen_repeats: 3,
  screen_visits: 4,
  press_retries: 2,
}
const GENERATION = {
  max_scenarios_per_journey: null,
  max_test_cases_per_application: null,
  max_heal_attempts: 3,
  screenshot_capture: 'failed',
}

function openMenu(name: string) {
  fireEvent.click(screen.getByRole('button', { name: `Actions for ${name} environment` }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AppSettingsTab', () => {
  it('lists the default environment first, then the extras', () => {
    renderTab()

    const rows = screen.getAllByTestId(/^environment-row-/)
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual([
      'environment-row-production',
      'environment-row-UAT',
    ])
    expect(within(rows[0]).getByText('https://prod.example.com/signin')).toBeTruthy()
    expect(within(rows[1]).getByText('uat-account')).toBeTruthy()
  })

  it('lets a member edit every row but remove only the extra ones', () => {
    renderTab({ role: 'member' })

    openMenu('production')
    expect(screen.getByRole('menuitem', { name: 'Edit production environment' })).toBeTruthy()
    expect(screen.queryByRole('menuitem', { name: 'Remove production environment' })).toBeNull()
    openMenu('UAT')
    expect(screen.getByRole('menuitem', { name: 'Edit UAT environment' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Remove UAT environment' })).toBeTruthy()
  })

  it('adds through the one shared Add environment dialog', () => {
    const value = renderTab()

    fireEvent.click(screen.getByRole('button', { name: 'Add environment' }))

    expect(value.requestAdd).toHaveBeenCalledTimes(1)
  })

  it('is read-only for a viewer — no add, edit, remove, or password reveal', () => {
    renderTab({ role: 'viewer', canAdd: false })

    expect(screen.getAllByTestId(/^environment-row-/)).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'Add environment' })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Actions for / })).toBeNull()
    expect(screen.queryByRole('button', { name: /password for/ })).toBeNull()
  })

  it('hides the Add environment button when environments cannot be added to this app', () => {
    renderTab({ canAdd: false })

    expect(screen.queryByRole('button', { name: 'Add environment' })).toBeNull()
  })

  it('keeps passwords masked until revealed, and shows the one asked for', async () => {
    const calls = stubFetch((path) =>
      path.endsWith('/environments/env-1/reveal') ? { body: { password: 'uat-secret' } } : { body: {} },
    )
    renderTab()

    expect(screen.queryByText('uat-secret')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Show password for UAT' }))

    expect(await screen.findByText('uat-secret')).toBeTruthy()
    expect(calls).toEqual([{ path: '/applications/app-1/environments/env-1/reveal', method: 'POST' }])

    fireEvent.click(screen.getByRole('button', { name: 'Hide password for UAT' }))
    expect(screen.queryByText('uat-secret')).toBeNull()
  })

  it('reveals the default environment’s password through the application credentials route', async () => {
    const calls = stubFetch(() => ({ body: { password: 'prod-secret' } }))
    renderTab()

    fireEvent.click(screen.getByRole('button', { name: 'Show password for production' }))

    expect(await screen.findByText('prod-secret')).toBeTruthy()
    expect(calls[0].path).toBe('/applications/app-1/credentials/reveal')
  })

  it('shows no credentials for an environment that does not sign in', () => {
    renderTab({ environments: [{ ...DEFAULT_ENV, auth_method: 'none', username: null, login_url: null }] })

    const row = screen.getByTestId('environment-row-production')
    expect(within(row).queryByRole('button', { name: /password for/ })).toBeNull()
    expect(within(row).queryByRole('button', { name: /^Actions for / })).toBeNull()
  })

  it('removes an environment after confirmation, then refreshes the list', async () => {
    const calls = stubFetch(() => ({ status: 204 }))
    const value = renderTab()

    openMenu('UAT')
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove UAT environment' }))
    expect(screen.getByText('Remove UAT environment?')).toBeTruthy()
    expect(calls).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: 'OK, remove' }))

    await waitFor(() => expect(value.refresh).toHaveBeenCalled())
    expect(calls).toEqual([{ path: '/applications/app-1/environments/env-1', method: 'DELETE' }])
    expect(screen.queryByText('Remove UAT environment?')).toBeNull()
  })

  it('says why an environment with runs or schedules cannot be removed', async () => {
    stubFetch(() => ({ status: 409, body: { detail: 'ENVIRONMENT_IN_USE' } }))
    const value = renderTab()

    openMenu('UAT')
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove UAT environment' }))
    fireEvent.click(screen.getByRole('button', { name: 'OK, remove' }))

    expect((await screen.findByRole('alert')).textContent).toContain("has test runs or schedules, so it can't be removed")
    expect(value.refresh).not.toHaveBeenCalled()
  })

  it('keeps the environment when removal is cancelled', () => {
    const calls = stubFetch(() => ({ status: 204 }))
    const value = renderTab()

    openMenu('UAT')
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove UAT environment' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByText('Remove UAT environment?')).toBeNull()
    expect(calls).toEqual([])
    expect(value.refresh).not.toHaveBeenCalled()
  })

  it('opens on a hub of this application’s settings', () => {
    renderTab({ card: null })
    for (const title of ['Environment Settings', 'Explorer limits', 'Test case generation'])
      expect(screen.getByRole('button', { name: `Configure ${title}` })).toBeTruthy()
    expect(screen.queryByTestId(/^environment-row-/)).toBeNull()
  })

  it('shows Environment Settings under its own heading', () => {
    renderTab()
    expect(screen.getByRole('heading', { name: 'Environment Settings' })).toBeTruthy()
    fireEvent.click(screen.getByText('Back to Settings'))
    expect(screen.getByRole('button', { name: 'Configure Explorer limits' })).toBeTruthy()
  })

  it('loads and saves this application’s Explorer limits', async () => {
    const calls = stubFetch((path) => ({ body: path.endsWith('/settings') ? EXPLORER_LIMITS : {} }))
    renderTab({ role: 'admin', card: 'Explorer limits' })
    for (const group of ['Time', 'AI cost', 'Coverage', 'Accuracy', 'When to give up'])
      expect(await screen.findByText(group)).toBeTruthy()
    expect((screen.getByLabelText('Question wait') as HTMLSelectElement).value).toBe('30')
    // Waiting until you answer takes the mission time limit off.
    fireEvent.change(screen.getByLabelText('Question wait'), { target: { value: 'none' } })
    const mission = screen.getByLabelText('Mission time limit') as HTMLSelectElement
    expect(mission.value).toBe('none')
    expect(mission.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('AI budget per run (USD)'), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Configuration' }))
    await waitFor(() =>
      expect(calls).toContainEqual({ path: '/explorer/applications/app-1/settings', method: 'PUT' }),
    )
    const put = vi.mocked(fetch).mock.calls.find(([, init]) => (init as { method?: string })?.method === 'PUT')
    expect(JSON.parse(String((put![1] as { body: string }).body)).ai_budget_usd).toBe(25)
    expect(calls[0]).toEqual({ path: '/explorer/applications/app-1/settings', method: 'GET' })
  })

  it('saves this application’s test case generation settings', async () => {
    const calls = stubFetch(() => ({ body: GENERATION }))
    renderTab({ role: 'admin', card: 'Test case generation' })
    fireEvent.change(await screen.findByLabelText('Maximum self-heal attempts'), { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Configuration' }))
    await waitFor(() =>
      expect(calls).toContainEqual({ path: '/applications/app-1/generation-settings', method: 'PUT' }),
    )
  })

  it('shows the limits read-only to anyone but an admin', async () => {
    const calls = stubFetch(() => ({ body: EXPLORER_LIMITS }))
    renderTab({ role: 'member', card: 'Explorer limits' })
    expect(await screen.findByText('Only organization admins can change these settings.')).toBeTruthy()
    expect(screen.getByLabelText('Question wait').matches(':disabled')).toBe(true)  // the whole form
    expect(screen.queryByRole('button', { name: 'Save Configuration' })).toBeNull()
    expect(calls.every((c) => c.method === 'GET')).toBe(true)
  })

  it('saves this application’s sign-in credentials and refreshes its environments', async () => {
    const calls = stubFetch(() => ({ body: {} }))
    const value = renderTab({ card: 'Sign-in credentials' })
    expect((screen.getByLabelText('Environment') as HTMLInputElement).value).toBe('production')
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'qa-new' } })
    fireEvent.change(screen.getByLabelText('Password or token'), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: /Save credentials/ }))
    expect(await screen.findByText('Credentials saved.')).toBeTruthy()
    expect(calls).toContainEqual({ path: '/applications/app-1/credentials', method: 'PATCH' })
    expect(value.refresh).toHaveBeenCalled()
  })

  it('does not let a viewer change credentials', () => {
    renderTab({ role: 'viewer', card: 'Sign-in credentials' })
    expect(screen.getByText('Viewers can’t change credentials.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Save credentials/ })).toBeNull()
  })
})
