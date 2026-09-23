import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TeamMembers } from './TeamMembers'

const ADMIN = { name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' as const }

const MEMBERS = [
  { name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' as const, created_at: new Date(Date.now() - 90 * 86400_000).toISOString() },
  { name: 'Bob Builder', email: 'bob@example.com', role: 'member' as const, created_at: new Date(Date.now() - 3 * 86400_000).toISOString() },
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
    expect(screen.getByText('Admin')).toBeTruthy()
    // { selector: 'span' } disambiguates the role pill from the table's own
    // "Member" column header (a <div>), which shares the literal text.
    expect(screen.getByText('Member', { selector: 'span' })).toBeTruthy()
  })

  it('does not offer a remove action on your own row', async () => {
    stubFetch()
    render(<TeamMembers user={ADMIN} />)

    await screen.findByText('Bob Builder')
    expect(screen.getAllByTitle('More options')).toHaveLength(1)
  })

  it('removes a teammate', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      // `api.ts`'s `request()` always passes a truthy options object (it
      // merges in `credentials`/`headers` unconditionally) — `!init` never
      // actually matches a real GET call; check the unset `method` instead.
      if (url.endsWith('/team') && !init?.method) return { ok: true, status: 200, json: async () => MEMBERS }
      if (url.includes('/team/bob%40example.com') && init?.method === 'DELETE') {
        return { ok: true, status: 204, json: async () => undefined }
      }
      return { ok: true, status: 200, json: async () => [MEMBERS[0]] }
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<TeamMembers user={ADMIN} />)

    await screen.findByText('Bob Builder')
    fireEvent.click(screen.getByTitle('More options'))
    fireEvent.click(screen.getByText('Remove'))

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/team/bob%40example.com'), expect.objectContaining({ method: 'DELETE' })),
    )
  })
})
