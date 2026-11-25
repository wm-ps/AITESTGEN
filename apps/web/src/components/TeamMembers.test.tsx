import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TeamMembers } from './TeamMembers'

const ADMIN = { name: 'Ada Lovelace', email: 'ada@example.com', role: 'super_admin' as const }

const MEMBERS = [
  { name: 'Ada Lovelace', email: 'ada@example.com', role: 'super_admin' as const, created_at: new Date(Date.now() - 90 * 86400_000).toISOString(), teams: ['Default'] },
  { name: 'Bob Builder', email: 'bob@example.com', role: 'standard_user' as const, created_at: new Date(Date.now() - 3 * 86400_000).toISOString(), teams: ['Default', 'Payments'] },
]

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/team') && (!init || init.method === undefined)) {
        return { ok: true, status: 200, json: async () => MEMBERS }
      }
      if (url.includes('/team/') && init?.method === 'DELETE') {
        return { ok: true, status: 204, json: async () => undefined }
      }
      return { ok: true, status: 200, json: async () => ({}) }
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('TeamMembers', () => {
  it('lists the roster with roles, marking the signed-in user', async () => {
    stubFetch()
    render(<TeamMembers user={ADMIN} />)

    await screen.findByText('Bob Builder')
    expect(screen.getByText('(you)')).toBeTruthy()
    expect(screen.getByText('Super Admin')).toBeTruthy()
    // { selector: 'span' } disambiguates the role pill from the table's own
    // "Member" column header (a <div>), which shares the literal text.
    expect(screen.getByText('User', { selector: 'span' })).toBeTruthy()
  })

  it('offers no remove action on your own row, only stepping down', async () => {
    stubFetch()
    render(<TeamMembers user={ADMIN} />)

    await screen.findByText('Bob Builder')
    const menus = screen.getAllByTitle('More options')
    expect(menus).toHaveLength(2) // Bob's, and yours for stepping down
    fireEvent.click(menus[0]) // the first row is Ada (you)
    expect(screen.getByRole('menuitem', { name: 'Step down' })).toBeTruthy()
    expect(screen.queryByRole('menuitem', { name: 'Remove user' })).toBeNull()
  })

  it('shows each person’s teams, and “All teams” for a super admin', async () => {
    stubFetch()
    render(<TeamMembers user={ADMIN} />)

    await screen.findByText('Bob Builder')
    expect(screen.getByText('All teams')).toBeTruthy()
    expect(screen.getByText('Default, Payments')).toBeTruthy()
  })

  it('removes a teammate', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      // `api.ts`'s `request()` always passes a truthy options object (it
      // merges in `credentials`/`headers` unconditionally) — `!init` never
      // actually matches a real GET call; check the unset `method` instead.
      if (url.endsWith('/team') && !init?.method) return { ok: true, status: 200, json: async () => MEMBERS }
      if (url.endsWith('/removal-impact')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ name: 'Bob Builder', personal_applications: 2, people_losing_access: 1, team_applications_added: 3, teams: 2, schedules_without_recipient: 1 }),
        }
      }
      if (url.includes('/team/bob%40example.com') && init?.method === 'DELETE') {
        return { ok: true, status: 204, json: async () => undefined }
      }
      return { ok: true, status: 200, json: async () => [MEMBERS[0]] }
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<TeamMembers user={ADMIN} />)

    await screen.findByText('Bob Builder')
    fireEvent.click(screen.getAllByTitle('More options')[1])
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove user' }))

    // It warns first, with what goes — and deletes nothing until confirmed.
    expect(await screen.findByText(/permanently deletes their account/)).toBeTruthy()
    expect(await screen.findByText(/2 personal applications will be deleted, and 1 person they shared them with will lose access/)).toBeTruthy()
    expect(screen.getByText(/3 applications they added in teams stay with the team and go to its Team Admins/)).toBeTruthy()
    expect(screen.getByText(/They leave 2 teams/)).toBeTruthy()
    expect(screen.getByText(/1 schedule they created keep running but have no one to email the report to/)).toBeTruthy()
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE')).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Remove user' }))
    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/team/bob%40example.com'), expect.objectContaining({ method: 'DELETE' })),
    )
  })

  it('cancelling the warning removes nobody', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/team') && !init?.method) return { ok: true, status: 200, json: async () => MEMBERS }
      return { ok: true, status: 200, json: async () => ({ name: 'Bob Builder', personal_applications: 0, people_losing_access: 0, team_applications_added: 0, teams: 1, schedules_without_recipient: 0 }) }
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<TeamMembers user={ADMIN} />)

    await screen.findByText('Bob Builder')
    fireEvent.click(screen.getAllByTitle('More options')[1])
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove user' }))
    await screen.findByText(/permanently deletes their account/)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByText(/permanently deletes their account/)).toBeNull()
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE')).toBe(false)
  })
})
