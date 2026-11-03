import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EnvironmentRead } from '../../api'
import { EditEnvironmentDialog } from './EditEnvironmentDialog'

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
  login_url: 'https://uat.example.com/signin',
  is_default: false,
  auth_method: 'standard_login',
  username: 'uat-account',
}

type Handler = (body: unknown) => { status?: number; body: unknown }

function stubFetch(overrides: Record<string, Handler> = {}) {
  const handlers: Record<string, Handler> = {
    '/domains/check': () => ({ body: { allowed: true, host: 'x' } }),
    '/applications/test-connection': () => ({ body: { reachable: true, detail: null } }),
    '/applications/verify-credentials': () => ({ status: 202, body: { check_id: 'check-1' } }),
    '/applications/verify-credentials/check-1': () => ({ body: { status: 'valid', detail: null } }),
    '/applications/app-1/environments/env-1': () => ({ body: UAT }),
    '/applications/app-1/credentials': () => ({ body: {} }),
    ...overrides,
  }
  const calls: { method: string; path: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
      const path = new URL(url).pathname
      const body = init?.body ? JSON.parse(init.body) : undefined
      calls.push({ method: init?.method ?? 'GET', path, body })
      const key = Object.keys(handlers).find((suffix) => path.endsWith(suffix))
      const reply = key ? handlers[key](body) : { body: {} }
      const status = reply.status ?? 200
      return { ok: status < 400, status, json: async () => reply.body }
    }),
  )
  return calls
}

function renderDialog(environment: EnvironmentRead) {
  const onClose = vi.fn()
  const onSaved = vi.fn()
  render(
    <EditEnvironmentDialog
      applicationId="app-1"
      environment={environment}
      defaultEnvironment={DEFAULT_ENV}
      onClose={onClose}
      onSaved={onSaved}
    />,
  )
  return { onClose, onSaved }
}

const change = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
const save = () => fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('EditEnvironmentDialog', () => {
  it('prefills the environment and its saved password, and has nothing to save until something changes', async () => {
    stubFetch({ '/reveal': () => ({ body: { password: 'saved-secret' } }) })
    renderDialog(UAT)

    expect((screen.getByLabelText('Environment name') as HTMLInputElement).value).toBe('UAT')
    expect((screen.getByLabelText('Deployed URL') as HTMLInputElement).value).toBe('https://uat.example.com')
    expect((screen.getByLabelText('Username') as HTMLInputElement).value).toBe('uat-account')
    await waitFor(() => expect((screen.getByLabelText('Password') as HTMLInputElement).value).toBe('saved-secret'))
    expect((screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows "URL is reachable." under the URL when saving a changed URL', async () => {
    stubFetch()
    const { onSaved } = renderDialog(UAT)

    change('Deployed URL', 'https://uat2.example.com')
    change('Password', 'new-secret')
    save()

    expect(await screen.findByText('URL is reachable.')).toBeTruthy()
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('shows an unreachable URL under the URL, not at the bottom', async () => {
    stubFetch({ '/applications/test-connection': () => ({ body: { reachable: false, detail: 'Base URL did not respond' } }) })
    renderDialog(UAT)

    change('Deployed URL', 'https://uat2.example.com')
    change('Password', 'new-secret')
    save()

    expect(await screen.findByText('Base URL did not respond')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('saves a rename without any URL or login check', async () => {
    const calls = stubFetch()
    const { onSaved } = renderDialog(UAT)

    change('Environment name', 'UAT-2')
    save()

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(calls.filter((c) => !c.path.endsWith('/reveal') && (c.method !== 'GET' || !c.path.endsWith('/domains/check'))).map((c) => c.path.split('/applications')[1])).toEqual([
      '/app-1/environments/env-1',
    ])
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ name: 'UAT-2' })
  })

  it('needs the password again when the URL changes, and asks for it before checking anything', async () => {
    const calls = stubFetch()
    renderDialog(UAT)

    change('Deployed URL', 'https://uat2.example.com')
    save()

    expect((await screen.findByRole('alert')).textContent).toBe('Enter the password to check the new details')
    expect(calls.some((c) => c.path.endsWith('/test-connection'))).toBe(false)
  })

  it('checks the new URL and login with the new details, then saves only what changed', async () => {
    const calls = stubFetch()
    const { onSaved } = renderDialog(UAT)

    change('Deployed URL', 'https://uat2.example.com')
    change('Password', 'new-secret')
    save()

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(calls.find((c) => c.path.endsWith('/test-connection'))?.body).toEqual({ url: 'https://uat2.example.com' })
    expect(calls.find((c) => c.path.endsWith('/verify-credentials') && c.body)?.body).toEqual({
      url: 'https://uat2.example.com',
      login_url: 'https://uat.example.com/signin',
      username: 'uat-account',
      password: 'new-secret',
    })
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      url: 'https://uat2.example.com',
      password: 'new-secret',
    })
  })

  it('saves nothing when the new login is rejected', async () => {
    const calls = stubFetch({
      '/applications/verify-credentials/check-1': () => ({ body: { status: 'invalid', detail: null } }),
    })
    const { onSaved } = renderDialog(UAT)

    change('Password', 'wrong')
    save()

    expect((await screen.findByRole('alert')).textContent).toContain('username or password is incorrect')
    expect(onSaved).not.toHaveBeenCalled()
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
  })

  it('tells the user when a run is in progress on the environment', async () => {
    stubFetch({ '/applications/app-1/environments/env-1': () => ({ status: 409, body: { detail: 'ENVIRONMENT_RUNNING' } }) })
    renderDialog(UAT)

    change('Environment name', 'UAT-2')
    save()

    expect((await screen.findByRole('alert')).textContent).toContain('A test run is in progress')
  })

  it('lets the default environment change only its username and password', async () => {
    const calls = stubFetch()
    const { onSaved } = renderDialog(DEFAULT_ENV)

    expect((screen.getByLabelText('Environment name') as HTMLInputElement).readOnly).toBe(true)
    expect((screen.getByLabelText('Deployed URL') as HTMLInputElement).readOnly).toBe(true)
    expect((screen.getByLabelText('Login URL') as HTMLInputElement).readOnly).toBe(true)

    change('Password', 'rotated')
    save()

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    // The login is checked against the application's own URLs, then saved
    // through the credentials route.
    expect(calls.find((c) => c.path.endsWith('/verify-credentials') && c.body)?.body).toEqual({
      url: 'https://prod.example.com',
      login_url: 'https://prod.example.com/signin',
      username: 'qa-account',
      password: 'rotated',
    })
    expect(calls.find((c) => c.method === 'PATCH')).toMatchObject({
      path: expect.stringContaining('/applications/app-1/credentials'),
      body: { username: 'qa-account', password: 'rotated', mfa_enabled: false },
    })
  })

  it('discards the edit on Cancel', () => {
    const calls = stubFetch()
    const { onClose, onSaved } = renderDialog(UAT)

    change('Environment name', 'UAT-2')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onSaved).not.toHaveBeenCalled()
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
  })
})
