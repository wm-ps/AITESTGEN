import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EnvironmentRead } from '../../api'
import { PermissionsProvider } from '../../PermissionsContext'
import { WORKSPACE_TABS, Workspace, type WorkspaceTab } from './Workspace'

const DEFAULT_ENV: EnvironmentRead = {
  id: null,
  name: 'production',
  url: 'https://prod.example.com',
  login_url: null,
  is_default: true,
  auth_method: 'standard_login',
  username: 'qa-account',
}
const UAT: EnvironmentRead = {
  id: 'env-uat',
  name: 'UAT',
  url: 'https://uat.example.com',
  login_url: null,
  is_default: false,
  auth_method: 'standard_login',
  username: 'uat-account',
}

type Call = { method: string; path: string; body: unknown }

// Routes the endpoints a workspace touches; anything unknown gets an empty
// list/object. `environments` is mutable so an add can show up on refresh.
function stubApi({ environments, onPost }: { environments: EnvironmentRead[]; onPost?: (call: Call) => unknown }) {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
      const path = new URL(url).pathname
      const method = init?.method ?? 'GET'
      const body = init?.body ? JSON.parse(init.body) : undefined
      const call = { method, path, body }
      calls.push(call)
      const ok = (json: unknown, status = 200) => ({ ok: true, status, json: async () => json })

      if (path.endsWith('/environments') && method === 'GET') return ok(environments)
      if (path.endsWith('/environments') && method === 'POST') {
        const created = onPost?.(call) as EnvironmentRead
        environments.push(created)
        return ok(created, 201)
      }
      if (method === 'POST' && path.endsWith('/test-runs')) return ok({ started: true }, 202)
      if (path.endsWith('/test-suite-status')) return ok({ items: [], total: 3, page: 1, page_size: 1 })
      if (path.endsWith('/test-runs')) return ok({ items: [], next_cursor: null })
      if (path.endsWith('/domains/check')) return ok({ allowed: true, host: 'x' })
      if (path.endsWith('/applications/test-connection')) return ok({ reachable: true, detail: null })
      if (path.endsWith('/applications/verify-credentials') && method === 'POST') return ok({ check_id: 'c1' }, 202)
      if (path.endsWith('/applications/verify-credentials/c1')) return ok({ status: 'valid', detail: null })
      return ok([])
    }),
  )
  return calls
}

function renderWorkspace(activeTab: WorkspaceTab, role: 'member' | 'viewer' = 'member') {
  return render(
    <PermissionsProvider value={role}>
      <Workspace applicationId="app-1" applicationName="Acme" applicationUrl="https://prod.example.com" activeTab={activeTab} onActiveTabChange={() => {}} />
    </PermissionsProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Workspace environments', () => {
  it('puts Application settings right after Download project', () => {
    expect(WORKSPACE_TABS.map((tab) => tab.label).slice(-2)).toEqual(['Download project', 'Application settings'])
  })

  it('shows the application’s own environment and the extras under Application settings', async () => {
    stubApi({ environments: [DEFAULT_ENV, UAT] })
    renderWorkspace('settings')

    expect(await screen.findByTestId('environment-row-UAT')).toBeInTheDocument()
    expect(screen.getByTestId('environment-row-production')).toBeInTheDocument()
    expect(screen.getByText('Application settings', { selector: 'h1' })).toBeInTheDocument()
  })

  it('runs the suite on the environment picked in the Run dialog', async () => {
    const calls = stubApi({ environments: [DEFAULT_ENV, UAT] })
    renderWorkspace('runs')

    fireEvent.click(await screen.findByRole('button', { name: 'Run' }))
    await screen.findByRole('option', { name: 'UAT · uat.example.com' })
    fireEvent.change(screen.getByLabelText('Run on environment'), { target: { value: 'env-uat' } })
    fireEvent.click(screen.getByRole('button', { name: /All test cases/ }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path.endsWith('/test-runs'))).toBe(true))
    expect(calls.find((c) => c.method === 'POST' && c.path.endsWith('/test-runs'))?.body).toEqual({
      environment_id: 'env-uat',
    })
  })

  it('runs on the default environment with no body when nothing else is chosen', async () => {
    const calls = stubApi({ environments: [DEFAULT_ENV, UAT] })
    renderWorkspace('runs')

    fireEvent.click(await screen.findByRole('button', { name: 'Run' }))
    await screen.findByRole('option', { name: 'UAT · uat.example.com' })
    fireEvent.click(screen.getByRole('button', { name: /All test cases/ }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path.endsWith('/test-runs'))).toBe(true))
    expect(calls.find((c) => c.method === 'POST' && c.path.endsWith('/test-runs'))?.body).toBeUndefined()
  })

  it('adds an environment from the Run dialog’s picker, checking it first, and selects it', async () => {
    const environments = [DEFAULT_ENV]
    const calls = stubApi({
      environments,
      onPost: (call) => ({ ...UAT, ...(call.body as object) , id: 'env-new', is_default: false, login_url: null }),
    })
    renderWorkspace('runs')

    fireEvent.click(await screen.findByRole('button', { name: 'Run' }))
    const picker = await screen.findByLabelText('Run on environment')
    fireEvent.change(picker, { target: { value: '__add_new_environment__' } })

    const dialog = await screen.findByRole('dialog', { name: 'Add new environment' })
    fireEvent.change(within(dialog).getByLabelText('Environment name'), { target: { value: 'UAT' } })
    fireEvent.change(within(dialog).getByLabelText('Deployed URL'), { target: { value: 'https://uat.example.com' } })
    fireEvent.change(within(dialog).getByLabelText('Username'), { target: { value: 'uat-account' } })
    fireEvent.change(within(dialog).getByLabelText('Password'), { target: { value: 'uat-secret' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add Environment' }))

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Add new environment' })).toBeNull())
    expect((screen.getByLabelText('Run on environment') as HTMLSelectElement).value).toBe('env-new')
    const order = calls
      .filter((c) => /test-connection|verify-credentials|\/environments$/.test(c.path) && c.method === 'POST')
      .map((c) => c.path.split('/applications')[1])
    expect(order).toEqual(['/test-connection', '/verify-credentials', '/app-1/environments'])
  })

  it('discards a half-filled Add dialog on Cancel and offers no new environment', async () => {
    const calls = stubApi({ environments: [DEFAULT_ENV] })
    renderWorkspace('runs')

    fireEvent.click(await screen.findByRole('button', { name: 'Run' }))
    fireEvent.change(await screen.findByLabelText('Run on environment'), { target: { value: '__add_new_environment__' } })
    const dialog = await screen.findByRole('dialog', { name: 'Add new environment' })
    fireEvent.change(within(dialog).getByLabelText('Environment name'), { target: { value: 'UAT' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog', { name: 'Add new environment' })).toBeNull()
    expect(calls.some((c) => c.method === 'POST' && c.path.endsWith('/environments'))).toBe(false)
    const options = Array.from((screen.getByLabelText('Run on environment') as HTMLSelectElement).options).map((o) => o.text)
    expect(options).toEqual(['production · prod.example.com', '+ Add new environment'])
  })

  it('does not offer to add environments to a viewer', async () => {
    stubApi({ environments: [DEFAULT_ENV, UAT] })
    renderWorkspace('settings', 'viewer')

    expect(await screen.findByTestId('environment-row-UAT')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add environment' })).toBeNull()
  })
})
