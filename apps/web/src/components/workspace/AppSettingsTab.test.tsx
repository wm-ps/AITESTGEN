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
}: { role?: Role; environments?: EnvironmentRead[]; canAdd?: boolean } = {}) {
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

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AppSettingsTab', () => {
  it('lists the default environment first, badged, then the extras', () => {
    renderTab()

    const rows = screen.getAllByTestId(/^environment-row-/)
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual([
      'environment-row-production',
      'environment-row-UAT',
    ])
    expect(within(rows[0]).getByText('Default')).toBeTruthy()
    expect(within(rows[1]).queryByText('Default')).toBeNull()
    expect(within(rows[0]).getByText('https://prod.example.com/signin')).toBeTruthy()
    expect(within(rows[1]).getByText('uat-account')).toBeTruthy()
  })

  it('lets a member edit every row but remove only the extra ones', () => {
    renderTab({ role: 'member' })

    expect(screen.getByRole('button', { name: 'Edit production environment' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Edit UAT environment' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Remove UAT environment' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Remove production environment' })).toBeNull()
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
    expect(screen.queryByRole('button', { name: /^Edit / })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Remove / })).toBeNull()
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
    expect(within(row).queryByRole('button', { name: /^Edit / })).toBeNull()
  })

  it('removes an environment after confirmation, then refreshes the list', async () => {
    const calls = stubFetch(() => ({ status: 204 }))
    const value = renderTab()

    fireEvent.click(screen.getByRole('button', { name: 'Remove UAT environment' }))
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

    fireEvent.click(screen.getByRole('button', { name: 'Remove UAT environment' }))
    fireEvent.click(screen.getByRole('button', { name: 'OK, remove' }))

    expect((await screen.findByRole('alert')).textContent).toContain("has test runs or schedules, so it can't be removed")
    expect(value.refresh).not.toHaveBeenCalled()
  })

  it('keeps the environment when removal is cancelled', () => {
    const calls = stubFetch(() => ({ status: 204 }))
    const value = renderTab()

    fireEvent.click(screen.getByRole('button', { name: 'Remove UAT environment' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByText('Remove UAT environment?')).toBeNull()
    expect(calls).toEqual([])
    expect(value.refresh).not.toHaveBeenCalled()
  })
})
