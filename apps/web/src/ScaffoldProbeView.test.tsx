import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { ScaffoldProbeView } from './ScaffoldProbeView'

afterEach(() => {
  vi.restoreAllMocks()
})

test('renders the scaffold probe returned by the API', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        id: 'test-id-123',
        note: 'scaffold-ok',
        created_at: '2026-07-16T00:00:00Z',
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ),
  )

  render(<ScaffoldProbeView />)

  await waitFor(() => {
    expect(screen.getByText('id: test-id-123')).toBeTruthy()
  })
  expect(screen.getByText('note: scaffold-ok')).toBeTruthy()
})

test('shows an error when the API call fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 500 }))

  render(<ScaffoldProbeView />)

  await waitFor(() => {
    expect(screen.getByRole('alert')).toBeTruthy()
  })
})
