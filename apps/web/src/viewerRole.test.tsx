// Read-only "viewer" role in the UI: write actions are hidden (the API refuses
// them anyway — this is about not offering what can't be done), reads stay.
// Each component renders inside PermissionsProvider as App does.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Role } from './api'
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

function as(role: Role, ui: React.ReactElement) {
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

    as('member', <RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findByTitle('Retry this test with self-healing')).toBeInTheDocument()
    expect(screen.getByText('View report')).toBeInTheDocument()
  })

  it('shows no Run or Cancel run in the toolbar, even while a run is going', async () => {
    stubRuns('running')

    as('viewer', <Workspace applicationId="app-1" activeTab="runs" onActiveTabChange={() => {}} />)

    await screen.findAllByText('Run #3', { exact: false })
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(screen.queryByRole('button', { name: 'Run' })).toBeNull()
    expect(screen.queryByText('Running…')).toBeNull()
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

  it('shows a View only badge and hides Add application and Settings in the shell', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => [] })))
    const shell = (role: Role) =>
      as(
        role,
        <AppShell
          user={{ name: 'Vera Viewer', email: 'vera@example.com', role }}
          route="apps"
          crumb="Applications"
          onGoOverview={() => {}}
          onGoApps={() => {}}
          onAddApplication={() => {}}
          onOpenSettings={() => {}}
          onGoTeam={() => {}}
          onLogout={() => {}}
        >
          <div />
        </AppShell>,
      )

    const viewer = shell('viewer')
    expect(screen.getByText('View only')).toBeInTheDocument()
    expect(screen.queryByText('Add application')).toBeNull()
    expect(screen.queryByText('Settings')).toBeNull()
    viewer.unmount()

    shell('member')
    expect(screen.queryByText('View only')).toBeNull()
    expect(screen.getAllByText('Add application').length).toBeGreaterThan(0)
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })
})

describe('assigning the viewer role', () => {
  it('offers Viewer when inviting a teammate', () => {
    render(<InviteTeammateModal onClose={() => {}} />)

    expect(screen.getByText('Viewer')).toBeInTheDocument()
    expect(screen.getByText('Can view applications, test cases and run results — no changes.')).toBeInTheDocument()
  })

  it('changes a member to viewer from the Team members menu', async () => {
    let members = [
      { name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
      { name: 'Bob Builder', email: 'bob@example.com', role: 'member', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
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

    render(<TeamMembers user={{ name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' }} />)

    await screen.findByText('Bob Builder')
    fireEvent.click(screen.getByTitle('More options'))
    const menu = screen.getByRole('menu')
    expect(within(menu).getByRole('menuitemradio', { name: /Member/ })).toBeDisabled()
    fireEvent.click(within(menu).getByRole('menuitemradio', { name: /Viewer/ }))

    await waitFor(() => expect(screen.getByText('Viewer', { selector: 'span' })).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/team/bob%40example.com/role'),
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ role: 'viewer' }) }),
    )
  })

  it('shows the last-admin refusal from the server', async () => {
    const members = [
      { name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
      { name: 'Ann Admin', email: 'ann@example.com', role: 'admin', created_at: '2026-09-01T00:00:00Z', last_active_at: null },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) =>
        init?.method === 'PATCH'
          ? { ok: false, status: 409, json: async () => ({ detail: 'an organization needs at least one admin' }) }
          : { ok: true, status: 200, json: async () => members },
      ),
    )

    render(<TeamMembers user={{ name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' }} />)

    await screen.findByText('Ann Admin')
    fireEvent.click(screen.getByTitle('More options'))
    fireEvent.click(within(screen.getByRole('menu')).getByRole('menuitemradio', { name: /Viewer/ }))

    expect(await screen.findByText('an organization needs at least one admin')).toBeInTheDocument()
  })
})
