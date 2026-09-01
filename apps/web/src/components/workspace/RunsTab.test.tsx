import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RunsTab } from './RunsTab'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RunsTab', () => {
  it('renders the RUN column as #<run_number>', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/test-runs')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              items: [
                {
                  id: 'run-1',
                  run_number: 3,
                  status: 'completed',
                  trigger: 'Manual run',
                  pass_rate: 1,
                  health: { tier: 'good' },
                  total_count: 1,
                  passed_count: 1,
                  failed_count: 0,
                  timed_out_count: 0,
                  errored_count: 0,
                  blocked_count: 0,
                  blocked_reason: null,
                  environment_snapshot: 'staging',
                  target_base_url_snapshot: 'https://x.example.com',
                  created_at: '2026-09-01T00:00:00Z',
                  started_at: null,
                  completed_at: null,
                },
              ],
              next_cursor: null,
            }),
          }
        }
        return { ok: true, status: 200, json: async () => ({ available: true }) }
      }),
    )

    render(<RunsTab applicationId="app-1" />)

    await waitFor(() => expect(screen.getByText('#3')).toBeInTheDocument())
  })
})
