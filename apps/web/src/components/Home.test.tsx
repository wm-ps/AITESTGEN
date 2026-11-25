import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Home } from './Home'
import { WorkspaceProvider } from '../WorkspaceContext'
import { setActiveWorkspace, type MyWorkspacesRead } from '../api'

const USER = { name: 'Ada Lovelace', email: 'ada@example.com', role: 'super_admin' as const }

const BASE_APP = {
  url: 'https://example.com',
  login_url: null,
  environment: 'staging',
  auth_method: 'standard_login',
  created_at: new Date().toISOString(),
  discovery_run_id: 'run-1',
  discovery_status: 'complete',
  discovery_stage: 'analyzed',
  discovery_failure_reason: null,
  journey_count: 3,
  scenario_count: 3,
  scenario_journeys_covered: 3,
  last_test_run_status: 'completed',
  last_test_run_created_at: new Date().toISOString(),
  test_run_count: 1,
  recent_pass_rates: [0.95],
  suite_count: 1,
  test_case_count: 5,
  suites_generating_count: 0,
  live_exploration_generating: false,
  journeys_with_generation_error: 0,
  failed_journey_names: [] as string[],
}

const HEALTHY_APP = {
  ...BASE_APP,
  id: 'app-1',
  name: 'Checkout App',
  last_test_run_pass_rate: 0.95,
  last_test_run_health: { tier: 'healthy', headline: 'Healthy' },
}

function stubFetch(apps: unknown[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => apps })),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('Home applications table', () => {
  it('lists applications as table rows with their status', async () => {
    stubFetch([HEALTHY_APP])
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)

    await screen.findByText('Checkout App')
    expect(screen.getByText('https://example.com')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Application' })).toBeInTheDocument()
  })

  it('blocks opening an application whose domain is not approved and says so above the table', async () => {
    stubFetch([HEALTHY_APP, { ...HEALTHY_APP, id: 'app-2', name: 'Blocked App', domain_approved: false }])
    const onResume = vi.fn()
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={onResume} />)

    fireEvent.click((await screen.findByText('Blocked App')).closest('tr')!)

    expect((await screen.findByRole('alert')).textContent).toContain(
      "The domain for application ‘Blocked App’ is not whitelisted. Please contact your admin to get it approved.",
    )
    expect(onResume).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('Checkout App').closest('tr')!)
    expect(onResume).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows the empty state with no applications', async () => {
    stubFetch([])
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)

    await screen.findByText('Add your first application')
  })

  it('`[FIXED generation-stuck]` does not read a permanently-failed Journey as still generating', async () => {
    // 2 journeys total; 1 has a real Scenario, the other permanently failed
    // (generation_error set, retries exhausted) — never gets one. Before the
    // fix, `scenario_journeys_covered` (1) < `journey_count` (2) forever,
    // showing "Generating scenarios" with no way out. Both are now "done".
    stubFetch([
      {
        ...BASE_APP,
        id: 'app-stuck',
        name: 'Stuck App',
        journey_count: 2,
        scenario_count: 1,
        scenario_journeys_covered: 1,
        journeys_with_generation_error: 1,
        failed_journey_names: ['Broken Journey'],
        last_test_run_status: null,
        last_test_run_created_at: null,
        last_test_run_pass_rate: null,
        last_test_run_health: { tier: 'needs_attention', headline: 'No tests have run yet' },
        test_run_count: 0,
        recent_pass_rates: [],
        suite_count: 0,
        test_case_count: 0,
      },
    ])
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)

    await screen.findByText('Stuck App')
    expect(screen.getByText('Scenarios generated')).toBeInTheDocument()
    expect(screen.queryByText('Generating scenarios')).toBeNull()
  })

  it('`[ADDED generation-stuck notification]` shows a toast the poll a Journey is newly seen as failed, not on the first load', async () => {
    vi.useFakeTimers()
    let call = 0
    const firstResponse = [{ ...BASE_APP, id: 'app-1', name: 'Checkout App' }]
    const secondResponse = [
      { ...BASE_APP, id: 'app-1', name: 'Checkout App', journeys_with_generation_error: 1, failed_journey_names: ['Broken Journey'] },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        call += 1
        return { ok: true, status: 200, json: async () => (call === 1 ? firstResponse : secondResponse) }
      }),
    )
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)

    await vi.waitFor(() => expect(screen.getByText('Checkout App')).toBeInTheDocument())
    expect(screen.queryByText(/Scenario generation failed/)).toBeNull()

    await vi.advanceTimersByTimeAsync(15000)
    await vi.waitFor(() =>
      expect(
        screen.getByText('Scenario generation failed for "Broken Journey" in Checkout App — continuing with the remaining journeys.'),
      ).toBeInTheDocument(),
    )

    vi.useRealTimers()
  })
})

describe('Home access: roles, sharing and filters', () => {
  const ADDED = { ...HEALTHY_APP, id: 'a1', name: 'Added App', my_role: 'app_admin', added_by_me: true, shared_with_me: false, shared_with_count: 0 }
  const SHARED = { ...HEALTHY_APP, id: 'a2', name: 'Shared App', my_role: 'contributor', added_by_me: false, shared_with_me: true, shared_with_count: 2 }
  const GIVEN = { ...HEALTHY_APP, id: 'a3', name: 'Given App', my_role: 'app_admin', added_by_me: true, shared_with_me: false, shared_with_count: 1 }

  it('has no Your role column', async () => {
    stubFetch([ADDED, SHARED])
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)

    await screen.findByText('Added App')
    expect(screen.queryByRole('columnheader', { name: 'Your role' })).toBeNull()
    const sharedRow = screen.getByText('Shared App').closest('tr')!
    expect(within(sharedRow).queryByText('Contributor')).toBeNull()
  })

  it('offers Manage access in the row menu to application admins only', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => ({
        ok: true,
        status: 200,
        json: async () => (String(input).includes('/access') ? [] : [ADDED, SHARED]),
      })),
    )
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)
    await screen.findByText('Added App')

    const sharedRow = screen.getByText('Shared App').closest('tr')!
    expect(within(sharedRow).queryByTitle('More options')).toBeNull() // a Contributor has no menu, so no Manage access
    expect(screen.queryByLabelText(/Manage access to/)).toBeNull() // no share icon any more

    fireEvent.click(within(screen.getByText('Added App').closest('tr')!).getByTitle('More options'))
    fireEvent.click(await screen.findByRole('button', { name: 'Manage access' }))
    expect(await screen.findByRole('dialog', { name: 'Manage access' })).toBeInTheDocument()
  })

  it('does not open the application when Manage access or its dialog is clicked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => ({
        ok: true,
        status: 200,
        json: async () => (String(input).includes('/access') ? [] : [ADDED]),
      })),
    )
    const onResume = vi.fn()
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={onResume} />)
    await screen.findByText('Added App')

    fireEvent.click(screen.getByTitle('More options'))
    fireEvent.click(await screen.findByRole('button', { name: 'Manage access' }))
    fireEvent.click(await screen.findByRole('dialog', { name: 'Manage access' }))
    expect(onResume).not.toHaveBeenCalled()
  })

  it('filters by All, Shared with me, Added by me and Private, with a count on each', async () => {
    stubFetch([ADDED, SHARED, GIVEN])
    render(<Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />)
    await screen.findByText('Added App')

    const group = screen.getByRole('group', { name: 'Filter applications' })
    expect(within(group).getByRole('button', { name: 'All 3' })).toBeInTheDocument()
    expect(within(group).getByRole('button', { name: 'Shared with me 1' })).toBeInTheDocument()
    expect(within(group).getByRole('button', { name: 'Added by me 2' })).toBeInTheDocument()
    expect(within(group).getByRole('button', { name: 'Private 1' })).toBeInTheDocument()

    fireEvent.click(within(group).getByRole('button', { name: 'Shared with me 1' }))
    expect(screen.getByText('Shared App')).toBeInTheDocument()
    expect(screen.queryByText('Added App')).toBeNull()
    fireEvent.click(within(group).getByRole('button', { name: 'Private 1' }))
    expect(screen.getByText('Added App')).toBeInTheDocument()
    expect(screen.queryByText('Given App')).toBeNull()
  })
})

describe('Home in a workspace', () => {
  const DATA = (role: 'team_admin' | 'team_member', isDefault = true, personal = false): MyWorkspacesRead => ({
    personal: { id: 'personal', name: 'My workspace', kind: 'personal', role: null, is_default: false, application_count: 0 },
    teams: [{ id: 't1', name: 'Payments', kind: 'team', role, is_default: isDefault, application_count: 0 }],
    last_workspace: personal ? 'personal' : 't1',
  })

  function renderIn(data: MyWorkspacesRead, apps: unknown[] = []) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        return { ok: true, status: 200, json: async () => (url.endsWith('/me/workspaces') ? data : apps) }
      }),
    )
    render(
      <WorkspaceProvider notify={() => {}} onSwitched={() => {}}>
        <Home user={USER} onConnectApp={() => {}} onResumeApplication={() => {}} />
      </WorkspaceProvider>,
    )
  }

  afterEach(() => setActiveWorkspace(null))

  it('tells people where the existing applications went, once, in the Default team', async () => {
    renderIn(DATA('team_member'), [HEALTHY_APP])
    expect(await screen.findByText(/now live in the/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByText(/now live in the/)).toBeNull()
    expect(localStorage.getItem('vantage.defaultTeamBanner')).toBe('dismissed')
  })

  it('has no banner outside the Default team', async () => {
    renderIn(DATA('team_member', false), [HEALTHY_APP])
    await screen.findByText('Checkout App')
    expect(screen.queryByText(/now live in the/)).toBeNull()
  })

  it.each([
    ['team_member', 'No applications shared with you yet', 'Ask a Team Admin or the person who added the app.'],
    ['team_admin', 'No applications added to this team yet', null],
  ] as const)('explains an empty team to a %s', async (role, title, body) => {
    renderIn(DATA(role, false))
    expect(await screen.findByText(title)).toBeInTheDocument()
    if (body) expect(screen.getByText(body)).toBeInTheDocument()
  })

  it('explains an empty personal workspace', async () => {
    renderIn(DATA('team_member', false, true))
    expect(await screen.findByText('No applications yet')).toBeInTheDocument()
    expect(screen.getByText('Add your own, or ask someone to share one with your account.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: /Add application/ })).toBeInTheDocument())
  })
})
