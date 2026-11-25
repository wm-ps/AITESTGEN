import { useEffect } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setActiveWorkspace, type MyWorkspacesRead, type UserRead } from '../api'
import { WorkspaceProvider } from '../WorkspaceContext'
import { AccountMenu } from './AccountMenu'

const DATA: MyWorkspacesRead = {
  personal: { id: 'personal', name: 'My workspace', kind: 'personal', role: null, is_default: false, application_count: 1 },
  teams: [
    { id: 't-default', name: 'Default', kind: 'team', role: 'team_member', is_default: true, application_count: 3 },
    { id: 't-pay', name: 'Payments', kind: 'team', role: 'team_admin', is_default: false, application_count: 2 },
  ],
  last_workspace: null,
}
const USER: UserRead = { name: 'Ada Lovelace', email: 'ada@example.com', role: 'standard_user' }

let mounts = 0
function Probe() {
  useEffect(() => {
    mounts += 1
  }, [])
  return <span>probe</span>
}

function stub(data: MyWorkspacesRead = DATA) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/me/workspaces')) return { ok: true, status: 200, json: async () => data }
    if (url.endsWith('/me/workspace')) return { ok: true, status: 204, json: async () => undefined }
    return { ok: true, status: 200, json: async () => ({}) }
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderSwitcher(user: UserRead = USER, notify = vi.fn(), onSwitched = vi.fn(), onLogout = vi.fn()) {
  render(
    <WorkspaceProvider notify={notify} onSwitched={onSwitched}>
      <AccountMenu user={user} onLogout={onLogout} />
      <Probe />
    </WorkspaceProvider>,
  )
  return { notify, onSwitched, onLogout }
}

beforeEach(() => {
  mounts = 0
  window.localStorage.clear()
})
afterEach(() => {
  setActiveWorkspace(null)
  vi.unstubAllGlobals()
})

const AVATAR = { name: 'AL' }

describe('AccountMenu', () => {
  it('in a team: shows the team under your name and lists your other workspaces, not the one you are in', async () => {
    stub()
    renderSwitcher()

    fireEvent.click(await screen.findByRole('button', AVATAR))
    const menu = screen.getByRole('menu', { name: 'Account' })
    expect(within(menu).getByText('Ada Lovelace')).toBeTruthy()
    expect(within(menu).getByText('ada@example.com')).toBeTruthy()
    expect(screen.getAllByText('Default').length).toBeGreaterThan(0) // on the button

    const teams = within(menu).getByRole('group', { name: 'Your Teams' })
    expect(within(teams).getByRole('menuitem', { name: /Ada Lovelace \(Personal\)/ })).toBeTruthy()
    expect(within(teams).getByRole('menuitem', { name: /Payments/ })).toBeTruthy()
    expect(within(teams).queryByRole('menuitem', { name: /Default/ })).toBeNull() // already here
    expect(screen.queryByRole('menuitem', { name: 'Manage teams' })).toBeNull() // Teams lives in the sidebar
    expect(screen.getByRole('menuitem', { name: 'Log out' })).toBeTruthy()
  })

  it('in your personal workspace: shows your name and “(Personal)”, with every team to switch to', async () => {
    stub({ ...DATA, last_workspace: 'personal' })
    renderSwitcher()

    fireEvent.click(await screen.findByRole('button', AVATAR))
    const menu = screen.getByRole('menu', { name: 'Account' })
    expect(within(menu).getByText('(Personal)')).toBeTruthy()
    expect(within(menu).queryByText('Personal workspace')).toBeNull()
    const teams = within(menu).getByRole('group', { name: 'Your Teams' })
    expect(within(teams).getByRole('menuitem', { name: /Default/ })).toBeTruthy()
    expect(within(teams).getByRole('menuitem', { name: /Payments/ })).toBeTruthy()
    expect(within(teams).queryByRole('menuitem', { name: /Personal/ })).toBeNull()
  })

  it('switching remembers the choice, tells the server and the user, and remounts the app', async () => {
    const fetchMock = stub()
    const { notify, onSwitched } = renderSwitcher()
    await screen.findByRole('button', AVATAR)
    expect(mounts).toBe(1)

    fireEvent.click(screen.getByRole('button', AVATAR))
    fireEvent.click(screen.getByRole('menuitem', { name: /Payments/ }))

    await waitFor(() => expect(notify).toHaveBeenCalledWith('Switched to Payments'))
    expect(onSwitched).toHaveBeenCalledTimes(1)
    expect(mounts).toBe(2) // everything below the provider started fresh
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/me/workspace'),
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ workspace: 't-pay' }) }),
    )
    expect(screen.queryByRole('menu')).toBeNull() // picking a team closes the menu

    // From now on every request names the workspace.
    fireEvent.click(screen.getByRole('button', AVATAR))
    fireEvent.click(screen.getByRole('menuitem', { name: /\(Personal\)/ }))
    await waitFor(() => expect(notify).toHaveBeenCalledWith('Switched to your personal workspace'))
    fireEvent.click(screen.getByRole('button', AVATAR))
    expect(screen.getByText('(Personal)')).toBeTruthy()
  })

  it('sends the active workspace as X-Team-Id on later requests', async () => {
    const fetchMock = stub({ ...DATA, last_workspace: 't-pay' })
    renderSwitcher()
    await screen.findByRole('button', AVATAR)

    const { api } = await import('../api')
    await api.getMyWorkspaces()

    const lastCall = fetchMock.mock.calls.at(-1)
    expect((lastCall?.[1] as RequestInit).headers).toMatchObject({ 'X-Team-Id': 't-pay' })
  })

  it('falls back to the personal workspace, with a notice, when the remembered team is gone', async () => {
    const fetchMock = stub({ ...DATA, last_workspace: 't-gone' })
    const { notify, onSwitched } = renderSwitcher()

    await screen.findByRole('button', AVATAR)
    expect(notify).toHaveBeenCalledWith('You were removed from that team. Opened your personal workspace.')
    expect(onSwitched).toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/me/workspace'),
      expect.objectContaining({ body: JSON.stringify({ workspace: 'personal' }) }),
    )
  })

  it('says when the role in a team has changed since the last visit', async () => {
    window.localStorage.setItem('vantage.workspace.roles', JSON.stringify({ 't-pay': 'team_member', 't-default': 'team_member' }))
    stub()
    const { notify } = renderSwitcher()

    await screen.findByRole('button', AVATAR)
    expect(notify).toHaveBeenCalledWith('Your role in Payments changed to Team Admin')
    expect(notify).not.toHaveBeenCalledWith(expect.stringContaining('Default'))
  })

  it('does not offer “Manage teams” even to a super admin — the sidebar has Teams', async () => {
    const admin: UserRead = { ...USER, role: 'super_admin' }
    stub({
      ...DATA,
      teams: DATA.teams.map((t) => ({ ...t, role: 'super_admin' as const })),
    })
    const { onLogout } = renderSwitcher(admin)

    fireEvent.click(await screen.findByRole('button', AVATAR))
    expect(screen.queryByRole('menuitem', { name: 'Manage teams' })).toBeNull()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Log out' }))
    expect(onLogout).toHaveBeenCalled()
  })

  it('still works as a plain account menu outside a workspace provider', () => {
    const onLogout = vi.fn()
    render(<AccountMenu user={USER} onLogout={onLogout} />)
    fireEvent.click(screen.getByRole('button', AVATAR))
    expect(screen.queryByRole('group', { name: 'Your Teams' })).toBeNull()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Log out' }))
    expect(onLogout).toHaveBeenCalled()
  })
})
