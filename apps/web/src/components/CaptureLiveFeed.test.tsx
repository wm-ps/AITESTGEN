import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CaptureLiveFeed } from './CaptureLiveFeed'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('CaptureLiveFeed', () => {
  it('renders captured items newest-first in monospace', async () => {
    const rows = [
      { kind: 'api_call', summary: 'GET /api/newer', created_at: '2026-01-01T00:00:02Z' },
      { kind: 'page', summary: 'Home (/older)', created_at: '2026-01-01T00:00:01Z' },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => rows }),
    )

    render(<CaptureLiveFeed discoveryRunId="run-1" active={false} />)

    await waitFor(() => {
      expect(screen.getByText(/api_call/)).toBeTruthy()
    })
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0].textContent).toContain('api_call')
    expect((items[0] as HTMLElement).style.fontFamily).toBe('var(--font-mono)')
    expect(items[1].textContent).toContain('page')
  })

  it('renders nothing before the first successful poll', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }))
    const { container } = render(<CaptureLiveFeed discoveryRunId="run-1" active={false} />)
    expect(container.firstChild).toBeNull()
  })
})
