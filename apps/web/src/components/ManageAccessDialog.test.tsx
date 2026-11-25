import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AccessEntryRead } from '../api'
import { ManageAccessDialog } from './ManageAccessDialog'

const ENTRIES: AccessEntryRead[] = [
  { name: 'Maya Adder', email: 'maya@example.com', role: 'app_admin', locked: true, reason: 'Added by' },
  { name: 'Tina Lead', email: 'tina@example.com', role: 'app_admin', locked: true, reason: 'Team Admin' },
  { name: 'Raj Reader', email: 'raj@example.com', role: 'viewer', locked: false, reason: null },
]

type Call = { method: string; path: string; body?: unknown }

function stub(entries: AccessEntryRead[] = ENTRIES) {
  const calls: Call[] = []
  let rows = [...entries]
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input))
      const path = decodeURIComponent(url.pathname)
      const method = init?.method ?? 'GET'
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ method, path: decodeURIComponent(url.pathname + url.search), body })
      if (url.pathname.endsWith('/access/candidates')) {
        return { ok: true, status: 200, json: async () => [{ name: 'Zoe Newcomer', email: 'zoe@example.com' }] }
      }
      if (method === 'POST' && url.pathname.endsWith('/access')) {
        rows = [...rows, { name: 'Zoe Newcomer', email: body.email, role: body.role, locked: false, reason: null }]
        return { ok: true, status: 201, json: async () => rows.at(-1) }
      }
      if (method === 'PATCH') {
        rows = rows.map((r) => (path.endsWith(r.email) ? { ...r, role: body.role } : r))
        return { ok: true, status: 200, json: async () => rows.find((r) => path.endsWith(r.email)) }
      }
      if (method === 'DELETE') {
        rows = rows.filter((r) => !path.endsWith(r.email))
        return { ok: true, status: 204, json: async () => undefined }
      }
      return { ok: true, status: 200, json: async () => rows }
    }),
  )
  return calls
}

function open(onClose = vi.fn(), onChanged = vi.fn()) {
  render(
    <ManageAccessDialog applicationId="app-1" applicationName="Checkout" onClose={onClose} onChanged={onChanged} />,
  )
  return { onClose, onChanged }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ManageAccessDialog', () => {
  it('shows the application, its team and who has access, with the adder and team admins locked', async () => {
    stub()
    open()

    const dialog = await screen.findByRole('dialog', { name: 'Manage access' })
    expect(within(dialog).getByText('Checkout')).toBeTruthy()
    expect(await within(dialog).findByText('3 people have access')).toBeTruthy()
    expect(within(dialog).getByText('Added by')).toBeTruthy()
    expect(within(dialog).getByText('Team Admin')).toBeTruthy()
    // Locked rows can't be edited or removed; the shared one can.
    expect(within(screen.getByTestId('access-row-maya@example.com')).getByLabelText('Locked')).toBeTruthy()
    expect(within(screen.getByTestId('access-row-maya@example.com')).queryByLabelText(/Change role/)).toBeNull()
    expect(within(screen.getByTestId('access-row-raj@example.com')).getByLabelText('Change role for Raj Reader')).toBeTruthy()
  })

  it('shares with a person picked from the type-ahead, as a Viewer unless chosen otherwise', async () => {
    const calls = stub()
    const { onChanged } = open()
    await screen.findByText('3 people have access')

    const share = screen.getByRole('button', { name: 'Share' })
    expect(share).toBeDisabled() // nobody picked yet
    expect((screen.getByLabelText('Role') as HTMLSelectElement).value).toBe('viewer')

    fireEvent.change(screen.getByLabelText('Person to share with'), { target: { value: 'zo' } })
    // The matched part of a suggestion is bold, which splits its text: look at the content, not the name.
    const option = await within(await screen.findByRole('listbox', { name: 'Person to share with suggestions' })).findByRole('option')
    expect(option.textContent).toContain('Zoe Newcomer')
    fireEvent.click(option)
    expect(screen.getByRole('button', { name: 'Share' })).toBeEnabled()
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'contributor' } })
    fireEvent.click(screen.getByRole('button', { name: 'Share' }))

    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'POST', path: '/applications/app-1/access', body: { email: 'zoe@example.com', role: 'contributor' } }),
    )
    expect(await screen.findByText('Zoe Newcomer added')).toBeTruthy()
    expect(onChanged).toHaveBeenCalled()
  })

  it('changes a role in place: select, save, and nothing else edits at the same time', async () => {
    const calls = stub()
    open()
    await screen.findByText('3 people have access')

    fireEvent.click(screen.getByLabelText('Change role for Raj Reader'))
    fireEvent.change(screen.getByLabelText('Role for Raj Reader'), { target: { value: 'contributor' } })
    fireEvent.click(screen.getByLabelText('Save role for Raj Reader'))

    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'PATCH', path: '/applications/app-1/access/raj@example.com', body: { role: 'contributor' } }),
    )
    expect(await screen.findByText('Raj Reader is now Contributor')).toBeTruthy()
  })

  it('removes access', async () => {
    const calls = stub()
    open()
    await screen.findByText('3 people have access')

    fireEvent.click(screen.getByLabelText('Remove access for Raj Reader'))

    await waitFor(() => expect(calls).toContainEqual({ method: 'DELETE', path: '/applications/app-1/access/raj@example.com', body: undefined }))
    expect(await screen.findByText('Raj Reader removed')).toBeTruthy()
    expect(await screen.findByText('2 people have access')).toBeTruthy()
  })

  it('Escape cancels a role edit first and only then closes; a click outside never closes it', async () => {
    stub()
    const { onClose } = open()
    await screen.findByText('3 people have access')

    fireEvent.click(screen.getByLabelText('Change role for Raj Reader'))
    expect(screen.getByLabelText('Role for Raj Reader')).toBeTruthy()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByLabelText('Role for Raj Reader')).toBeNull()
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('dialog').parentElement as HTMLElement) // the backdrop
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes from the X', async () => {
    stub()
    const { onClose } = open()
    await screen.findByText('3 people have access')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
