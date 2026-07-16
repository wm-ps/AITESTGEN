import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function mockFetchOnce(body: unknown, ok: boolean, status: number) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => body,
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('renders Sign in when there is no session', async () => {
    vi.stubGlobal('fetch', mockFetchOnce({ detail: 'not signed in' }, false, 401))
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy()
    })
  })

  it('renders Home with the top bar and avatar menu when signed in', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchOnce({ name: 'Ada Lovelace', email: 'ada@example.com' }, true, 200),
    )
    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Welcome back, Ada' })).toBeTruthy()
    })
    expect(screen.getByText('Start a New Project')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'AL' }))

    expect(screen.getByText('ada@example.com')).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Log out' })).toBeTruthy()
  })
})
