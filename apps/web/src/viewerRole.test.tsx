// Read-only "viewer" role on an application in the UI: write actions are hidden
// (the API refuses them anyway — this is about not offering what can't be done),
// reads stay. Each component renders inside PermissionsProvider as App does,
// with the role on the application that is open.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AppRole } from './api'
import { PermissionsProvider } from './PermissionsContext'
import { AppShell } from './components/shell/AppShell'
import { InviteTeammateModal } from './components/InviteTeammateModal'
import { TeamMembers } from './components/TeamMembers'
import { RunsTab } from './components/workspace/RunsTab'
import { SchedulesTab } from './components/workspace/SchedulesTab'
import { Workspace } from './components/workspace/Workspace'

afterEach(() => {
  vi.unstubAllGlobals()
})

function as(role: AppRole, ui: React.ReactElement) {
  return render(<PermissionsProvider value={role}>{ui}</PermissionsProvider>)
}

const RUN = {
  id: 'run-1',
  run_number: 3,
  name: '#3 - Full Suite Run',
  trigger: 'Manual run',
  pass_rate: 0,
  health: { tier: 'critical', headline: 'Failing' },
  total_count: 1,
  passed_count: 0,
  failed_count: 1,
  timed_out_count: 0,
  errored_count: 0,
  blocked_count: 0,
  blocked_reason: null,
  environment_snapshot: 'staging',
  target_base_url_snapshot: 'https://x.example.com',
  created_at: '2026-09-01T00:00:00Z',
  started_at: null,
  completed_at: null,
  allure_report_available: true,
}

const FAILED_RESULT = {
  id: 'result-1',
  scenario_name: 'Submits a claim',
  journey_name: 'Claims',
  test_case_number: 7,
  status: 'failed',
  duration_ms: 1200,
  error_message: 'TimeoutError: locator.click: Timeout 15000ms exceeded.',
  stack_trace: null,
  blocked_reason: null,
  auto_heal_attempt_count: 0,
  manual_heal_attempt_count: 0,
  healed_test_asset_id: null,
  auto_heal_attempt_cap: 2,
  max_heal_attempts: 3,
  heal_blocked_reason: null,
  heal_in_progress: false,
  heal_kind: null,
}

function stubRuns(status: 'completed' | 'running') {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('/test-runs/run-1')) {
        return { ok: true, status: 200, json: async () => ({ ...RUN, status, results: [FAILED_RESULT] }) }
      }
      if (url.includes('/test-runs')) {
        return { ok: true, status: 200, json: async () => ({ items: [{ ...RUN, status }], next_cursor: null }) }
      }
      if (url.includes('/test-suite-status')) {
        return { ok: true, status: 200, json: async () => ({ items: [], total: 1, page: 1, page_size: 1 }) }
      }
      return { ok: true, status: 200, json: async () => ({ available: true }) }
    }),
  )
}

describe('viewer role', () => {
  it('shows no Retry with self-healing and no View report on a run', async () => {
    stubRuns('completed')

    as('viewer', <RunsTab applicationId="app-1" initialRunId="run-1" />)

    await screen.findByText('Submits a claim', { exact: false })
    expect(screen.queryByTitle('Retry this test with self-healing')).toBeNull()
    expect(screen.queryByText('View report')).toBeNull()
    // The result itself is still there to read.
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(0)
  })

  it('still offers Retry and View report to a member', async () => {
    stubRuns('completed')

    as('contributor', <RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findByTitle('Retry this test with self-healing')).toBeInTheDocument()
    expect(screen.getByText('View report')).toBeInTheDocument()
  })

  it('shows no Run or Cancel run in the toolbar, even while a run is going', async () => {
    stubRuns('running')

    as('viewer', <Workspace applicationId="app-1" activeTab="runs" onActiveTabChange={() => {}} />)

    await screen.findAllByText('Run #3', { exact: false })
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(screen.queryByRole('button', { name: 'Run' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Running' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Cancel run' })).toBeNull()
  })

  it('lists schedules and their next run, with no schedule controls', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 'sched-1',
            name: 'Nightly Regression',
            cadence_type: 'daily',
            hour: 2,
            minute: 30,
            days_of_week: [],
            day_of_month: null,
            cron_expression: null,
            time_zone: 'Asia/Kolkata',
            enabled: true,
            cadence_label: 'Every day at 02:30 (Asia/Kolkata)',
            next_run_at: '2026-09-03T02:30:00Z',
            created_by_name: 'Tester',
            created_at: '2026-09-01T00:00:00Z',
          },
        ],
      })),
    )

    as('viewer', <SchedulesTab applicationId="app-1" />)

    await screen.findByText('Nightly Regression')
    expect(screen.getByText('Every day at 02:30 (Asia/Kolkata)')).toBeInTheDocument()
    expect(screen.getByText('On')).toBeInTheDocument()
    expect(screen.queryByRole('switch')).toBeNull()
    expect(screen.queryByText('New schedule')).toBeNull()
    expect(screen.queryByTitle('More options')).toBeNull()
  })

  it('shows Activity in the sidebar to a super admin only', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => [] })))
    const shell = (role: 'super_admin' | 'standard_user') =>
      as(
        'app_admin',
        <AppShell
          user={{ name: 'Sam', email: 'sam@example.com', role }}
          route="apps"
          crumb="Applications"
          onGoOverview={() => {}}
          onGoApps={() => {}}
          onGoActivity={() => {}}
          onLogout={() => {}}
        >
          <div />
        </AppShell>,
      )
    const admin = shell('super_admin')
    expect(screen.getByText('Activity')).toBeInTheDocument()
    admin.unmount()
    shell('standard_user')
    expect(screen.queryByText('Activity')).toBeNull()
  })

  it('shows the Configuration heading only when something sits under it', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => [] })))
    const shell = (role: 'super_admin' | 'standard_user', withSettings: boolean, withTeams: boolean) =>
      as(
        'contributor',
        <AppShell
          user={{ name: 'Sam', email: 'sam@example.com', role }}
          route="apps"
          crumb="Applications"
          onGoOverview={() => {}}
          onGoApps={() => {}}
          onAddApplication={() => {}}
          onOpenSettings={withSettings ? () => {} : undefined}
          onGoTeams={withTeams ? () => {} : undefined}
          onLogout={() => {}}
        >
          <div />
        </AppShell>,
      )
    // Someone with no item under it (a plain team member) gets no empty heading.
    const none = shell('standard_user', false, false)
    expect(screen.queryByText('Configuration')).toBeNull()
    none.unmount()
    // Settings alone, or Teams for a super admin, keep it.
    const settings = shell('standard_user', true, false)
    expect(screen.getByText('Configuration')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
    settings.unmount()
    shell('super_admin', false, true)
    expect(screen.getByText('Configuration')).toBeInTheDocument()
    expect(screen.getByText('Teams')).toBeInTheDocument()
  })

  it('shows a View only badge and hides Add application and Settings in the shell', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => [] })))
    const shell = (role: AppRole) =>
      as(
        role,
        <AppShell
          user={{ name: 'Vera Viewer', email: 'vera@example.com', role: 'standard_user' }}
          route="apps"
          crumb="Applications"
          onGoOverview={() => {}}
          onGoApps={() => {}}
          onAddApplication={() => {}}
          onOpenSettings={() => {}}
          onGoTeam={() => {}}
          onGoActivity={() => {}}
          onLogout={() => {}}
        >
          <div />
        </AppShell>,
      )

    const viewer = shell('viewer')
    expect(screen.queryByText('Activity')).toBeNull() // super admins only
    expect(screen.getByText('View only')).toBeInTheDocument()
    expect(screen.queryByText('Add application')).toBeNull()
    expect(screen.queryByText('Settings')).toBeNull()
    viewer.unmount()

    shell('contributor')
    expect(screen.queryByText('View only')).toBeNull()
    expect(screen.getAllByText('Add application').length).toBeGreaterThan(0)
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })
})

describe('invite email validation', () => {
  it('blocks an invalid email with an inline error and sends a trimmed valid one', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 201, json: async () => ({}) }))
    vi.stubGlobal('fetch', fetchMock)
    render(<InviteTeammateModal onClose={() => {}} />)
    const input = screen.getByPlaceholderText('Enter their email')

    fireEvent.change(input, { target: { value: 'foo@bar' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send invite' }))
    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: '  a@b.co  ' } })
    expect(screen.queryByText('Enter a valid email address')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Send invite' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(JSON.parse(String((fetchMock.mock.calls[0] as unknown[])[1] && ((fetchMock.mock.calls[0] as unknown[])[1] as RequestInit).body)).email).toBe('a@b.co')
  })
})

describe('organisation roles', () => {
  it('offers only User and Super Admin when inviting a teammate', () => {
    render(<InviteTeammateModal onClose={() => {}} />)

    expect(screen.getByText('User')).toBeInTheDocument()
    expect(screen.getByText('Super Admin')).toBeInTheDocument()
    // Read-only access is a per-application role, given when an application is shared.
    expect(screen.queryByText('Viewer')).toBeNull()
  })

  it('promotes a user to Super Admin from the Team members menu', async () => {
    let members = [
      { name: 'Ada Lovelace', email: 'ada@example.com', role: 'super_admin', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
      { name: 'Bob Builder', email: 'bob@example.com', role: 'standard_user', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
    ]
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'PATCH' && url.endsWith('/team/bob%40example.com/role')) {
        const role = JSON.parse(String(init.body)).role
        members = members.map((m) => (m.email === 'bob@example.com' ? { ...m, role } : m))
        return { ok: true, status: 200, json: async () => members[1] }
      }
      return { ok: true, status: 200, json: async () => members }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<TeamMembers user={{ name: 'Ada Lovelace', email: 'ada@example.com', role: 'super_admin' }} />)

    await screen.findByText('Bob Builder')
    fireEvent.click(screen.getAllByTitle('More options')[1])
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit role' }))
    const dialog = await screen.findByRole('dialog', { name: 'Edit role' })
    // Nothing to save until the role changes.
    expect(within(dialog).getByRole('button', { name: 'Update role' })).toBeDisabled()
    fireEvent.click(within(dialog).getByLabelText(/Super Admin/))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Update role' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/team/bob%40example.com/role'),
        expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ role: 'super_admin' }) }),
      ),
    )
    // Both people now carry the Super Admin pill.
    await waitFor(() => expect(screen.getAllByText('Super Admin', { selector: 'span' })).toHaveLength(2))
  })

  it('shows the last-admin refusal from the server', async () => {
    const members = [
      { name: 'Ada Lovelace', email: 'ada@example.com', role: 'super_admin', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
      { name: 'Ann Admin', email: 'ann@example.com', role: 'super_admin', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) =>
        init?.method === 'PATCH'
          ? { ok: false, status: 409, json: async () => ({ detail: 'an organization needs at least one admin' }) }
          : { ok: true, status: 200, json: async () => members },
      ),
    )

    render(<TeamMembers user={{ name: 'Ada Lovelace', email: 'ada@example.com', role: 'super_admin' }} />)

    await screen.findByText('Ann Admin')
    fireEvent.click(screen.getAllByTitle('More options')[1])
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit role' }))
    const dialog = await screen.findByRole('dialog', { name: 'Edit role' })
    fireEvent.click(within(dialog).getByLabelText(/^User/))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Update role' }))
    // Demoting a Super Admin is confirmed first.
    const confirm = await screen.findByRole('dialog', { name: 'Change Ann Admin to User?' })
    fireEvent.click(within(confirm).getByRole('button', { name: 'Change to User' }))

    expect(await screen.findByText('an organization needs at least one admin')).toBeInTheDocument()
  })

  it('asks before turning a Super Admin into a User and changes nothing until confirmed', async () => {
    const members = [
      { name: 'Ada Lovelace', email: 'ada@example.com', role: 'super_admin', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
      { name: 'Ann Admin', email: 'ann@example.com', role: 'super_admin', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
    ]
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'PATCH'
        ? { ok: true, status: 200, json: async () => ({ ...members[1], role: 'standard_user' }) }
        : { ok: true, status: 200, json: async () => members },
    )
    vi.stubGlobal('fetch', fetchMock)
    const patches = () => fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'PATCH')

    render(<TeamMembers user={{ name: 'Ada Lovelace', email: 'ada@example.com', role: 'super_admin' }} />)
    await screen.findByText('Ann Admin')

    // Cancel: no request.
    fireEvent.click(screen.getAllByTitle('More options')[1])
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit role' }))
    let dialog = await screen.findByRole('dialog', { name: 'Edit role' })
    fireEvent.click(within(dialog).getByLabelText(/^User/))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Update role' }))
    const confirm = await screen.findByRole('dialog', { name: 'Change Ann Admin to User?' })
    expect(within(confirm).getByText(/lose access to team applications/)).toBeInTheDocument()
    expect(within(confirm).getByText(/keep their personal workspace/)).toBeInTheDocument()
    expect(patches()).toHaveLength(0)
    fireEvent.click(within(confirm).getByRole('button', { name: 'Cancel' }))
    expect(patches()).toHaveLength(0)

    // Confirm: one request.
    fireEvent.click(screen.getAllByTitle('More options')[1])
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit role' }))
    dialog = await screen.findByRole('dialog', { name: 'Edit role' })
    fireEvent.click(within(dialog).getByLabelText(/^User/))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Update role' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Change Ann Admin to User?' })).getByRole('button', { name: 'Change to User' }))
    await waitFor(() => expect(patches()).toHaveLength(1))
    expect(patches()[0][1]).toEqual(expect.objectContaining({ body: JSON.stringify({ role: 'standard_user' }) }))
  })
})
