import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setActiveWorkspace, type MyWorkspacesRead, type TeamApplicationRead, type TeamPersonRead, type TeamRead } from '../api'
import { WorkspaceProvider } from '../WorkspaceContext'
import { MembersGrid, MyTeam, Teams } from './Teams'

const PAYMENTS: TeamRead = { id: 't-pay', name: 'Payments', is_default: false, team_admins: ['Tina Lead'], member_count: 2, application_count: 1 }
const DEFAULT: TeamRead = { id: 't-def', name: 'Migrated', is_default: true, team_admins: ['Boss Person'], member_count: 3, application_count: 4 }

const PEOPLE = [
  { name: 'Tina Lead', email: 'tina@example.com', role: 'standard_user', created_at: '2026-01-01T00:00:00Z', last_active_at: null },
  { name: 'Maya Maker', email: 'maya@example.com', role: 'standard_user', created_at: '2026-01-01T00:00:00Z', last_active_at: null },
  { name: 'Raj Reader', email: 'raj@example.com', role: 'standard_user', created_at: '2026-01-01T00:00:00Z', last_active_at: null },
]
const MEMBERS: TeamPersonRead[] = [
  { name: 'Tina Lead', email: 'tina@example.com', role: 'team_admin' },
  { name: 'Maya Maker', email: 'maya@example.com', role: 'team_member' },
]

describe('Super Admin members', () => {
  it('has no menu and reads as access to all apps', () => {
    render(
      <MembersGrid
        members={[{ name: 'Sue Root', email: 'sue@example.com', role: 'team_admin', is_super_admin: true, app_count: 3 }, ...MEMBERS]}
        team={PAYMENTS}
        canManage
        query=""
        onChanged={() => {}}
        onError={() => {}}
      />,
    )
    expect(screen.getByText('Sue Root')).toBeTruthy()
    expect(screen.getAllByText('Access to all apps')).toHaveLength(2)
    expect(screen.queryByLabelText('Actions for Sue Root')).toBeNull()
    expect(screen.getByLabelText('Actions for Maya Maker')).toBeTruthy()
  })
})
const APPLICATIONS: TeamApplicationRead[] = [
  { id: 'app-1', name: 'Checkout', url: 'https://shop.example.com', added_by_name: 'Maya Maker', people: ['Maya Maker', 'Tina Lead'], people_count: 2, my_role: 'app_admin' },
]

type Call = { method: string; path: string; body?: unknown }

function stub(options: { teams?: TeamRead[]; onMutate?: (call: Call) => { status: number; body?: unknown } | undefined } = {}) {
  const calls: Call[] = []
  const teams = options.teams ?? [DEFAULT, PAYMENTS]
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input))
      const path = decodeURIComponent(url.pathname)
      const method = init?.method ?? 'GET'
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      const call = { method, path, body }
      calls.push(call)
      const custom = method === 'GET' ? undefined : options.onMutate?.(call)
      if (custom) return { ok: custom.status < 400, status: custom.status, json: async () => custom.body }
      if (method === 'POST' && path === '/teams') {
        return { ok: true, status: 201, json: async () => ({ id: 't-new', name: body.name, is_default: false, team_admins: ['Tina Lead'], member_count: 1, application_count: 0 }) }
      }
      if (method === 'POST' && path.endsWith('/members')) return { ok: true, status: 201, json: async () => ({ name: 'Raj Reader', email: body.email, role: body.role }) }
      if (method !== 'GET') return { ok: true, status: method === 'DELETE' ? 204 : 200, json: async () => ({ ...MEMBERS[1], role: body?.role ?? 'team_member' }) }
      if (path === '/teams') return { ok: true, status: 200, json: async () => teams }
      if (path === '/team') return { ok: true, status: 200, json: async () => PEOPLE }
      if (path.endsWith('/members/candidates')) {
        const q = (url.searchParams.get('q') ?? '').toLowerCase()
        const rows = PEOPLE.filter((p) => p.name.toLowerCase().includes(q) || p.email.toLowerCase().includes(q))
        return { ok: true, status: 200, json: async () => rows.map(({ name, email }) => ({ name, email })) }
      }
      if (path.endsWith('/members')) return { ok: true, status: 200, json: async () => MEMBERS }
      if (path.endsWith('/applications')) return { ok: true, status: 200, json: async () => APPLICATIONS }
      if (path === '/me/workspaces') return { ok: true, status: 200, json: async () => WORKSPACES }
      if (path.startsWith('/teams/')) return { ok: true, status: 200, json: async () => teams.find((t) => path.includes(t.id)) }
      return { ok: true, status: 200, json: async () => ({}) }
    }),
  )
  return calls
}

const WORKSPACES: MyWorkspacesRead = {
  personal: { id: 'personal', name: 'My workspace', kind: 'personal', role: null, is_default: false, application_count: 0 },
  teams: [{ id: 't-pay', name: 'Payments', kind: 'team', role: 'team_admin', is_default: false, application_count: 1 }],
  last_workspace: 't-pay',
}

beforeEach(() => window.localStorage.clear())
afterEach(() => {
  setActiveWorkspace(null)
  vi.unstubAllGlobals()
})

describe('Teams (super admin)', () => {
  it('lists teams with their admins and counts, and filters by team or admin name', async () => {
    stub()
    render(<Teams />)

    expect(await screen.findByText('Payments')).toBeTruthy()
    expect(screen.getByText('Migrated')).toBeTruthy() // no special "Default" badge
    expect(screen.getByText('Tina Lead')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Search teams'), { target: { value: 'tina' } })
    expect(screen.queryByText('Migrated')).toBeNull()
    expect(screen.getByText('Payments')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Search teams'), { target: { value: 'nothing' } })
    expect(screen.getByText('No teams match your search.')).toBeTruthy()
  })

  it('needs a name and at least one Team Admin before a team can be created, then opens it', async () => {
    const calls = stub()
    render(<Teams />)
    fireEvent.click(await screen.findByRole('button', { name: /Create team/ }))

    const dialog = await screen.findByRole('dialog', { name: 'Create team' })
    const create = within(dialog).getByRole('button', { name: 'Create team' })
    expect(create).toBeDisabled()

    fireEvent.change(within(dialog).getByLabelText('Team name'), { target: { value: 'Growth' } })
    expect(create).toBeDisabled() // still no Team Admin

    fireEvent.change(within(dialog).getByLabelText('Team Admins'), { target: { value: 'tin' } })
    fireEvent.click(await screen.findByRole('option'))
    expect(within(dialog).getByLabelText('Remove Tina Lead')).toBeTruthy() // the chip
    expect(create).toBeEnabled()

    fireEvent.click(create)
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'POST', path: '/teams', body: { name: 'Growth', team_admin_emails: ['tina@example.com'] } }),
    )
    // The new team's page opens.
    expect(await screen.findByRole('heading', { name: 'Growth' })).toBeTruthy()
  })

  it('opens a team: members with their roles, applications read-only, and a way back', async () => {
    stub()
    render(<Teams />)
    fireEvent.click(await screen.findByText('Payments'))

    expect(await screen.findByRole('heading', { name: 'Payments' })).toBeTruthy()
    expect(await screen.findByText('Maya Maker')).toBeTruthy()
    expect(screen.getByText('Access to all apps')).toBeTruthy()
    expect(screen.getByText('Access to 0 apps')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: /Applications/ }))
    expect(await screen.findByText('Checkout')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /All teams/ }))
    expect(await screen.findByRole('heading', { name: 'Teams' })).toBeTruthy()
  })

  it('adds a person from the type-ahead with a role', async () => {
    const calls = stub()
    render(<Teams />)
    fireEvent.click(await screen.findByText('Payments'))
    await screen.findByText('Maya Maker')

    fireEvent.click(screen.getByRole('button', { name: /Add users/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Add team member' })
    expect(within(dialog).getByRole('button', { name: 'Add member' })).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('Email address'), { target: { value: 'raj' } })
    // Only people not already in the team are offered.
    const suggestions = await screen.findByRole('listbox', { name: 'Email address suggestions' })
    const options = await within(suggestions).findAllByRole('option')
    expect(options).toHaveLength(1)
    fireEvent.click(options[0])
    fireEvent.change(within(dialog).getByLabelText('Role'), { target: { value: 'team_admin' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add member' }))

    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'POST', path: '/teams/t-pay/members', body: { email: 'raj@example.com', role: 'team_admin' } }),
    )
    expect(await screen.findByText('Raj Reader added to Payments')).toBeTruthy()
  })

  it('edits a role and removes a person after confirming', async () => {
    const calls = stub()
    render(<Teams />)
    fireEvent.click(await screen.findByText('Payments'))
    await screen.findByText('Maya Maker')

    fireEvent.click(screen.getByLabelText('Actions for Maya Maker'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit role' }))
    const edit = await screen.findByRole('dialog', { name: 'Edit role' })
    expect(within(edit).getByRole('button', { name: 'Update role' })).toBeDisabled()
    fireEvent.click(within(edit).getByLabelText(/Team Admin/))
    fireEvent.click(within(edit).getByRole('button', { name: 'Update role' }))
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'PATCH', path: '/teams/t-pay/members/maya@example.com', body: { role: 'team_admin' } }),
    )

    fireEvent.click(await screen.findByLabelText('Actions for Maya Maker'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove from team' }))
    const remove = await screen.findByRole('dialog', { name: 'Remove from team' })
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false) // nothing happens until confirmed
    fireEvent.click(within(remove).getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(calls).toContainEqual({ method: 'DELETE', path: '/teams/t-pay/members/maya@example.com', body: undefined }))
  })

  it('shows the server’s refusal when it would leave a team without a Team Admin', async () => {
    stub({
      onMutate: (call) =>
        call.method === 'DELETE' ? { status: 409, body: { detail: 'Tina Lead is the only Team Admin of Payments. Assign another Team Admin first.' } } : undefined,
    })
    render(<Teams />)
    fireEvent.click(await screen.findByText('Payments'))
    await screen.findByText('Tina Lead', { selector: 'span' })

    fireEvent.click(screen.getByLabelText('Actions for Tina Lead'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove from team' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Remove from team' })).getByRole('button', { name: 'Remove' }))

    expect(await screen.findByText('Tina Lead is the only Team Admin of Payments. Assign another Team Admin first.')).toBeTruthy()
  })

  it('offers View team and Delete team on each row', async () => {
    stub()
    render(<Teams />)
    await screen.findByText('Payments')

    fireEvent.click(screen.getByLabelText('Actions for Payments'))
    expect(screen.getByRole('menuitem', { name: 'View team' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Delete team' })).toBeTruthy()
    fireEvent.click(screen.getByRole('menuitem', { name: 'View team' }))
    expect(await screen.findByText('All teams')).toBeTruthy()
  })

  it('does not delete a team that still has applications; it says to clean them up first', async () => {
    const calls = stub()
    render(<Teams />)
    await screen.findByText('Payments')

    fireEvent.click(screen.getByLabelText('Actions for Payments'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete team' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete team' })
    expect(within(dialog).getByText(/still has 1 application/)).toBeTruthy()
    expect(within(dialog).queryByRole('button', { name: 'Delete team' })).toBeNull()
    fireEvent.click(within(dialog).getAllByRole('button', { name: 'Close' }).at(-1)!) // the footer button; the X is the other
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
  })

  it('deletes an empty team only after confirming', async () => {
    const empty: TeamRead = { ...PAYMENTS, application_count: 0 }
    const calls = stub({ teams: [DEFAULT, empty] })
    render(<Teams />)
    await screen.findByText('Payments')

    fireEvent.click(screen.getByLabelText('Actions for Payments'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete team' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete team' })
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false) // nothing happens until confirmed
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete team' }))

    await waitFor(() => expect(calls).toContainEqual({ method: 'DELETE', path: '/teams/t-pay', body: undefined }))
    await waitFor(() => expect(screen.queryByText('Payments')).toBeNull())
  })

  it('shows the server’s refusal if an application turned up meanwhile', async () => {
    const empty: TeamRead = { ...PAYMENTS, application_count: 0 }
    stub({
      teams: [DEFAULT, empty],
      onMutate: (call) => (call.method === 'DELETE' ? { status: 409, body: { detail: 'This team still has 1 application. Delete or move them before deleting the team.' } } : undefined),
    })
    render(<Teams />)
    await screen.findByText('Payments')

    fireEvent.click(screen.getByLabelText('Actions for Payments'))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete team' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Delete team' })).getByRole('button', { name: 'Delete team' }))

    expect(await screen.findByText('This team still has 1 application. Delete or move them before deleting the team.')).toBeTruthy()
    expect(screen.getAllByText('Payments').length).toBeGreaterThan(0) // still listed (and named in the dialog)
  })
})

describe('My team (a team admin)', () => {
  it('lets a team admin add users and edit roles in their own team', async () => {
    const calls = stub()
    render(
      <WorkspaceProvider notify={() => {}} onSwitched={() => {}}>
        <MyTeam />
      </WorkspaceProvider>,
    )

    expect(await screen.findByRole('heading', { name: 'Payments' })).toBeTruthy()
    expect(await screen.findByText('Maya Maker')).toBeTruthy()
    expect(screen.getByText('Access to 0 apps')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Add users/ })).toBeTruthy()
    expect(screen.getAllByTitle('More options').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /All teams/ })).toBeNull()

    // The people lookup is the team's own (a Team Admin can't read the org-wide list).
    fireEvent.click(screen.getByRole('button', { name: /Add users/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Add team member' })
    fireEvent.change(within(dialog).getByLabelText('Email address'), { target: { value: 'raj' } })
    const suggestions = await screen.findByRole('listbox', { name: 'Email address suggestions' })
    expect(await within(suggestions).findAllByRole('option')).toHaveLength(1)
    expect(calls.some((c) => c.path === '/team')).toBe(false)
    expect(calls).toContainEqual({ method: 'GET', path: '/teams/t-pay/members/candidates', body: undefined })
  })
})
