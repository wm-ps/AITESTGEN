import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EnvironmentRead } from '../../api'
import { AddEnvironmentDialog } from './AddEnvironmentDialog'

const DEFAULT_WITH_LOGIN: EnvironmentRead = {
  id: null,
  name: 'production',
  url: 'https://prod.example.com',
  login_url: 'https://prod.example.com/signin',
  is_default: true,
  auth_method: 'standard_login',
  username: 'qa-account',
}

const CREATED: EnvironmentRead = {
  id: 'env-1',
  name: 'UAT',
  url: 'https://uat.example.com',
  login_url: 'https://uat.example.com/signin',
  is_default: false,
  auth_method: 'standard_login',
  username: 'uat-account',
}

type Handler = (body: unknown) => { status?: number; body: unknown }

// Routes `fetch` by the end of the path and remembers every call in order.
function stubFetch(handlers: Record<string, Handler>) {
  const calls: { path: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: { body?: string }) => {
      const path = new URL(url).pathname
      const body = init?.body ? JSON.parse(init.body) : undefined
      calls.push({ path, body })
      const key = Object.keys(handlers).find((suffix) => path.endsWith(suffix))
      const reply = key ? handlers[key](body) : { body: {} }
      const status = reply.status ?? 200
      return { ok: status < 400, status, json: async () => reply.body }
    }),
  )
  return calls
}

const HAPPY: Record<string, Handler> = {
  '/domains/check': () => ({ body: { allowed: true, host: 'uat.example.com' } }),
  '/applications/test-connection': () => ({ body: { reachable: true, detail: null } }),
  '/applications/verify-credentials': () => ({ status: 202, body: { check_id: 'check-1' } }),
  '/applications/verify-credentials/check-1': () => ({ body: { status: 'valid', detail: null } }),
  '/applications/app-1/environments': () => ({ status: 201, body: CREATED }),
}

function fill(values: Record<string, string>) {
  for (const [label, value] of Object.entries(values)) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  }
}

function fillAll() {
  fill({
    'Environment name': 'UAT',
    'Deployed URL': 'https://uat.example.com',
    'Login URL': 'https://uat.example.com/signin',
    Username: 'uat-account',
    Password: 'uat-secret',
  })
}

function renderDialog(defaultEnvironment: EnvironmentRead = DEFAULT_WITH_LOGIN) {
  const onClose = vi.fn()
  const onAdded = vi.fn()
  render(
    <AddEnvironmentDialog
      applicationId="app-1"
      defaultEnvironment={defaultEnvironment}
      onClose={onClose}
      onAdded={onAdded}
    />,
  )
  return { onClose, onAdded }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AddEnvironmentDialog', () => {
  it('asks for the same login details the default has, and a login URL when it has one', () => {
    renderDialog()

    for (const label of ['Environment name', 'Deployed URL', 'Login URL', 'Username', 'Password']) {
      expect(screen.getByText(label, { selector: 'span.label-required' })).toBeTruthy()
    }
    expect(screen.queryByText(/optional/)).toBeNull()
  })

  it('makes the login URL optional and drops the credentials when the default has no sign-in', () => {
    renderDialog({ ...DEFAULT_WITH_LOGIN, auth_method: 'none', login_url: null, username: null })

    expect(screen.queryByLabelText('Username')).toBeNull()
    expect(screen.queryByLabelText('Password')).toBeNull()
    expect(screen.getByText(/optional/)).toBeTruthy()
    expect(screen.getByText('Deployed URL', { selector: 'span.label-required' })).toBeTruthy()
  })

  it('uses instructions for placeholders, never made-up example values', () => {
    renderDialog()

    expect(screen.getByLabelText('Environment name').getAttribute('placeholder')).toBe('Enter the environment name')
    expect(screen.getByLabelText('Deployed URL').getAttribute('placeholder')).toBe('Enter the deployed URL')
    expect(screen.getByLabelText('Login URL').getAttribute('placeholder')).toBe('Enter the login URL')
    expect(screen.getByLabelText('Username').getAttribute('placeholder')).toBe('Enter the username')
  })

  it('names the first missing field and checks nothing', async () => {
    const calls = stubFetch(HAPPY)
    renderDialog()

    fill({ 'Environment name': 'UAT', 'Deployed URL': 'https://uat.example.com' })
    fireEvent.click(screen.getByRole('button', { name: 'Add Environment' }))

    expect((await screen.findByRole('alert')).textContent).toBe('Enter the login URL')
    expect(calls.map((c) => c.path).filter((p) => p.includes('test-connection'))).toEqual([])
  })

  it('checks the URL, then the login with the environment’s own URLs, then saves', async () => {
    const calls = stubFetch(HAPPY)
    const { onAdded } = renderDialog()

    fillAll()
    fireEvent.click(screen.getByRole('button', { name: 'Add Environment' }))

    await waitFor(() => expect(onAdded).toHaveBeenCalledWith(CREATED))
    const steps = calls
      .filter((c) => !c.path.endsWith('/domains/check'))
      .map((c) => c.path.replace(/^.*\/applications/, '/applications'))
    expect(steps).toEqual([
      '/applications/test-connection',
      '/applications/verify-credentials',
      '/applications/verify-credentials/check-1',
      '/applications/app-1/environments',
    ])
    expect(calls.find((c) => c.path.endsWith('/test-connection'))?.body).toEqual({ url: 'https://uat.example.com' })
    expect(calls.find((c) => c.path.endsWith('/verify-credentials') && c.body)?.body).toEqual({
      url: 'https://uat.example.com',
      login_url: 'https://uat.example.com/signin',
      username: 'uat-account',
      password: 'uat-secret',
    })
    expect(calls.find((c) => c.path.endsWith('/app-1/environments'))?.body).toEqual({
      name: 'UAT',
      url: 'https://uat.example.com',
      login_url: 'https://uat.example.com/signin',
      username: 'uat-account',
      password: 'uat-secret',
    })
  })

  it('saves nothing when the application does not answer at that URL', async () => {
    const calls = stubFetch({
      ...HAPPY,
      '/applications/test-connection': () => ({ body: { reachable: false, detail: 'Base URL did not respond' } }),
    })
    const { onAdded } = renderDialog()

    fillAll()
    fireEvent.click(screen.getByRole('button', { name: 'Add Environment' }))

    expect((await screen.findByText('Base URL did not respond')).textContent).toBe('Base URL did not respond')
    expect(onAdded).not.toHaveBeenCalled()
    expect(calls.some((c) => c.path.endsWith('/app-1/environments'))).toBe(false)
    expect(calls.some((c) => c.path.endsWith('/verify-credentials'))).toBe(false)
  })

  it('saves nothing when the login does not work, and lets the user try again', async () => {
    const calls = stubFetch({
      ...HAPPY,
      '/applications/verify-credentials/check-1': () => ({ body: { status: 'invalid', detail: null } }),
    })
    const { onAdded } = renderDialog()

    fillAll()
    fireEvent.click(screen.getByRole('button', { name: 'Add Environment' }))

    expect((await screen.findByRole('alert')).textContent).toContain('username or password is incorrect')
    expect(onAdded).not.toHaveBeenCalled()
    expect(calls.some((c) => c.path.endsWith('/app-1/environments'))).toBe(false)
    expect((screen.getByRole('button', { name: 'Add Environment' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('saves nothing when the login cannot be confirmed', async () => {
    const calls = stubFetch({
      ...HAPPY,
      '/applications/verify-credentials': () => ({ status: 503, body: { detail: 'DISCOVERY_UNAVAILABLE' } }),
    })
    const { onAdded } = renderDialog()

    fillAll()
    fireEvent.click(screen.getByRole('button', { name: 'Add Environment' }))

    expect((await screen.findByRole('alert')).textContent).toContain("couldn't confirm these credentials")
    expect(onAdded).not.toHaveBeenCalled()
    expect(calls.some((c) => c.path.endsWith('/app-1/environments'))).toBe(false)
  })

  it('blocks Add Environment for a domain the admin has not approved', async () => {
    stubFetch({ ...HAPPY, '/domains/check': () => ({ body: { allowed: false, host: 'uat.example.com' } }) })
    renderDialog()

    fillAll()

    expect((await screen.findByRole('alert')).textContent).toContain('Contact your admin')
    expect((screen.getByRole('button', { name: 'Add Environment' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('discards everything on Cancel — nothing is requested, nothing is saved', () => {
    const calls = stubFetch(HAPPY)
    const { onClose, onAdded } = renderDialog()

    fillAll()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onAdded).not.toHaveBeenCalled()
    expect(calls.some((c) => c.path.endsWith('/app-1/environments'))).toBe(false)
    expect(calls.some((c) => c.path.endsWith('/test-connection'))).toBe(false)
  })
})
