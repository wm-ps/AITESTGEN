import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setActiveWorkspace, type MyWorkspacesRead, type UserRead } from '../api'
import { WorkspaceProvider } from '../WorkspaceContext'
import { Settings } from './Settings'

const SETTINGS = {
  max_pages: 60,
  max_discovery_duration_minutes: 15,
  navigation_timeout_seconds: 30,
  interaction_level: 'normal',
  max_journeys: 12,
  max_scenarios_per_journey: null,
  max_test_cases_per_application: null,
  delete_project_after: '1_week',
  max_heal_attempts: 3,
  screenshot_capture: 'failed',
}

const USER: UserRead = { name: 'Tina Lead', email: 'tina@example.com', role: 'standard_user' }
const BOSS: UserRead = { name: 'Boss Person', email: 'boss@example.com', role: 'super_admin' }

const workspaces = (active: 'team_admin' | 'team_member' | 'super_admin' | 'personal'): MyWorkspacesRead => ({
  personal: { id: 'personal', name: 'My workspace', kind: 'personal', role: null, is_default: false, application_count: 0 },
  teams: [{ id: 't1', name: 'Payments', kind: 'team', role: active === 'personal' ? 'team_member' : active, is_default: false, application_count: 0 }],
  last_workspace: active === 'personal' ? 'personal' : 't1',
})

type Call = { method: string; path: string; body?: unknown; team: string | null }

function stub(data: MyWorkspacesRead, limits: unknown = { maximums: {}, min_delete_project_after: null, above: [] }) {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname
      const method = init?.method ?? 'GET'
      const headers = (init?.headers ?? {}) as Record<string, string>
      calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined, team: headers['X-Team-Id'] ?? null })
      const body =
        path === '/me/workspaces'
          ? data
          : path === '/settings'
            ? SETTINGS
            : path === '/organization/limits'
              ? limits
              : path === '/credentials' || path === '/domains'
                ? []
                : {}
      return { ok: true, status: 200, json: async () => body }
    }),
  )
  return calls
}

function renderSettings(user: UserRead, data: MyWorkspacesRead) {
  render(
    <WorkspaceProvider notify={() => {}} onSwitched={() => {}}>
      <Settings user={user} onCancel={() => {}} />
    </WorkspaceProvider>,
  )
}

beforeEach(() => window.localStorage.clear())
afterEach(() => {
  setActiveWorkspace(null)
  vi.unstubAllGlobals()
})

describe('Settings follow the workspace', () => {
  it('a team admin sees the team’s settings, labelled with the team', async () => {
    const data = workspaces('team_admin')
    const calls = stub(data)
    renderSettings(USER, data)

    expect(await screen.findByText('Payments team')).toBeInTheDocument()
    expect(screen.getByText('These settings apply only to the Payments team. Only Team Admins can change them.')).toBeInTheDocument()
    // Asked for with the team named, so the API answers for that team.
    await waitFor(() => expect(calls.some((c) => c.path === '/settings' && c.team === 't1')).toBe(true))
  })

  it('a team member is told settings are managed by Team Admins, and nothing is fetched', async () => {
    const data = workspaces('team_member')
    const calls = stub(data)
    renderSettings(USER, data)

    expect(await screen.findByText('Settings are managed by Team Admins')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to applications' })).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/settings')).toBe(false)
  })

  it('your personal workspace’s settings are yours', async () => {
    const data = workspaces('personal')
    stub(data)
    renderSettings(USER, data)

    expect(await screen.findByText('Personal workspace')).toBeInTheDocument()
    expect(screen.getByText('These settings apply only to your personal workspace.')).toBeInTheDocument()
  })

  it('only a super admin gets the organisation limits and the approved domains', async () => {
    const asTeamAdmin = workspaces('team_admin')
    stub(asTeamAdmin)
    const { unmount } = render(
      <WorkspaceProvider notify={() => {}} onSwitched={() => {}}>
        <Settings user={USER} onCancel={() => {}} />
      </WorkspaceProvider>,
    )
    await screen.findByText('Payments team')
    expect(screen.queryByRole('button', { name: 'Configure Organisation limits' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Configure Saved credentials' }))
    await screen.findByText(/Saved credentials/)
    expect(screen.queryByText(/Approved domains/i)).toBeNull()
    unmount()

    setActiveWorkspace(null)
    const asBoss = workspaces('super_admin')
    stub(asBoss)
    renderSettings(BOSS, asBoss)
    expect(await screen.findByRole('button', { name: 'Configure Organisation limits' })).toBeInTheDocument()
  })

  it('a super admin sets the limits; blanks mean no limit and settings above them are listed', async () => {
    const data = workspaces('super_admin')
    const calls = stub(data, {
      maximums: { max_heal_attempts: 3 },
      min_delete_project_after: '1_week',
      above: [{ scope: 'Checkout', setting: 'max_heal_attempts', value: 8, limit: 3 }],
    })
    renderSettings(BOSS, data)

    fireEvent.click(await screen.findByRole('button', { name: 'Configure Organisation limits' }))
    const heal = await screen.findByLabelText('Self-heal attempts per test')
    expect((heal as HTMLInputElement).value).toBe('3')
    expect((screen.getByLabelText('Shortest retention') as HTMLSelectElement).value).toBe('1_week')

    fireEvent.change(heal, { target: { value: '4' } })
    fireEvent.change(screen.getByLabelText('Explorer AI budget per run'), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save limits' }))

    await waitFor(() =>
      expect(calls).toContainEqual(
        expect.objectContaining({ method: 'PUT', path: '/organization/limits', body: { maximums: { ai_budget_usd: 25, max_heal_attempts: 4 }, min_delete_project_after: '1_week' } }),
      ),
    )
    expect(await screen.findByText('Limits saved.')).toBeInTheDocument()
    const note = screen.getByText(/above these limits/).closest('div')!
    expect(within(note).getByText('Checkout: max heal attempts is 8 (limit 3)')).toBeInTheDocument()
  })

  it('refuses a limit that is not a positive number', async () => {
    const data = workspaces('super_admin')
    const calls = stub(data)
    renderSettings(BOSS, data)

    fireEvent.click(await screen.findByRole('button', { name: 'Configure Organisation limits' }))
    fireEvent.change(await screen.findByLabelText('Self-heal attempts per test'), { target: { value: '-2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save limits' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Limits must be numbers above zero')
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })
})
