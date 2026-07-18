import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DiscoverJourneysPlaceholder } from './DiscoverJourneysPlaceholder'

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubCaptureFetch() {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }))
}

describe('DiscoverJourneysPlaceholder', () => {
  it('shows a status pill reading Running with a pulsing dot while the Discovery Run is running', () => {
    stubCaptureFetch()
    render(
      <DiscoverJourneysPlaceholder
        discoveryStatus="running"
        discoveryFailureReason={null}
        discoveryRunId="run-1"
      />,
    )

    expect(screen.getByText('Running')).toBeTruthy()
    expect(document.querySelector('.status-pill-pulse-dot')).toBeTruthy()
  })

  it('shows a re-authentication prompt distinct from a generic failure when session_expired', () => {
    stubCaptureFetch()
    render(
      <DiscoverJourneysPlaceholder
        discoveryStatus="failed"
        discoveryFailureReason="session_expired"
        discoveryRunId="run-1"
      />,
    )

    expect(screen.getByText('Failed')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('Re-authenticate')
  })

  it('shows a generic failure message (no re-auth prompt) for a non-session-expiry failure', () => {
    stubCaptureFetch()
    render(
      <DiscoverJourneysPlaceholder
        discoveryStatus="failed"
        discoveryFailureReason={null}
        discoveryRunId="run-1"
      />,
    )

    expect(screen.getByText('Failed')).toBeTruthy()
    const alert = screen.getByRole('alert')
    expect(alert.textContent).not.toContain('Re-authenticate')
    expect(alert.textContent).not.toContain('session_expired')
  })
})
