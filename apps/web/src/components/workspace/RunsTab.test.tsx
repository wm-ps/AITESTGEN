import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { TestRunRead } from '../../api'
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
                  name: '#3 - Full Suite Run',
                  status: 'completed',
                  trigger: 'Manual run',
                  pass_rate: 1,
                  health: { tier: 'healthy', headline: 'Healthy' },
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
                  allure_report_available: false,
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

    await waitFor(() => expect(screen.getByText('Run #3')).toBeInTheDocument())
  })

  // Self-healing only fixes broken locators in test actions — for an
  // assertion failure the Retry chip stays visible but disabled, with the
  // API's reason, instead of offering a heal that would be refused.
  function stubRunDetail(results: Array<Record<string, unknown>>) {
    const run = {
      id: 'run-1',
      run_number: 3,
      name: '#3 - Full Suite Run',
      status: 'completed',
      trigger: 'Manual run',
      pass_rate: 0,
      health: { tier: 'failing', headline: 'Failing' },
      total_count: results.length,
      passed_count: 0,
      failed_count: results.length,
      timed_out_count: 0,
      errored_count: 0,
      blocked_count: 0,
      blocked_reason: null,
      environment_snapshot: 'staging',
      target_base_url_snapshot: 'https://x.example.com',
      created_at: '2026-09-01T00:00:00Z',
      started_at: null,
      completed_at: null,
      allure_report_available: false,
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/test-runs/run-1')) {
          return { ok: true, status: 200, json: async () => ({ ...run, results }) }
        }
        if (url.includes('/test-runs')) {
          return { ok: true, status: 200, json: async () => ({ items: [run], next_cursor: null }) }
        }
        return { ok: true, status: 200, json: async () => ({ available: true }) }
      }),
    )
  }

  const failedResult = {
    scenario_name: 'Submits a claim',
    journey_name: 'Claims',
    test_case_number: 7,
    status: 'failed',
    duration_ms: 1200,
    stack_trace: null,
    blocked_reason: null,
    auto_heal_attempt_count: 0,
    manual_heal_attempt_count: 0,
    healed_test_asset_id: null,
    auto_heal_attempt_cap: 2,
    max_heal_attempts: 3,
  }

  it('shows Retry disabled with the reason for an assertion failure', async () => {
    stubRunDetail([
      {
        ...failedResult,
        id: 'result-1',
        error_message: 'Error: expect(locator).toBeVisible() failed',
        heal_blocked_reason: "Assertion failures aren't self-healed.",
      },
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const retry = await screen.findByRole('button', { name: /Retry with self-healing unavailable/ })
    expect(retry).toBeDisabled()
    expect(retry).toHaveAttribute('title', "Assertion failures aren't self-healed.")
  })

  it('keeps Retry enabled for a broken locator in an action', async () => {
    stubRunDetail([
      {
        ...failedResult,
        id: 'result-1',
        error_message: 'TimeoutError: locator.click: Timeout 15000ms exceeded.',
        heal_blocked_reason: null,
      },
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const retry = await screen.findByTitle('Retry this test with self-healing')
    expect(retry).toBeEnabled()
  })

  // The toolbar's Cancel run (Workspace) hands the cancelled run down — an
  // open detail shows it at once, and a stale "running" poll can't revert it.
  it('shows a run cancelled from the toolbar at once and never back as running', async () => {
    const running = {
      id: 'run-1',
      run_number: 4,
      name: '#4 - Full Suite Run',
      status: 'running',
      trigger: 'Manual run',
      pass_rate: null,
      health: { tier: 'healthy', headline: 'Healthy' },
      total_count: 2,
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
      allure_report_available: false,
      results: [],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/test-runs/run-1')) return { ok: true, status: 200, json: async () => running }
        if (url.includes('/test-runs')) {
          return { ok: true, status: 200, json: async () => ({ items: [running], next_cursor: null }) }
        }
        return { ok: true, status: 200, json: async () => ({ available: true }) }
      }),
    )

    const { rerender } = render(<RunsTab applicationId="app-1" initialRunId="run-1" />)
    await screen.findByText('Run #4')
    // The detail itself has no cancel control any more — it's in the toolbar.
    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()

    rerender(
      <RunsTab
        applicationId="app-1"
        initialRunId="run-1"
        cancelledRun={{ ...running, status: 'cancelled' } as TestRunRead}
      />,
    )

    await waitFor(() => expect(screen.getByText('Cancelled')).toBeInTheDocument())
    // The detail poll still answers "running" — the cancelled state holds.
    await new Promise((resolve) => setTimeout(resolve, 2500))
    expect(screen.getByText('Cancelled')).toBeInTheDocument()
  })

  // Self-healing in progress is server-driven (the result's live heal claim),
  // so it shows for automatic and manual heals, after a reload, in any tab.
  const healingResult = {
    ...failedResult,
    id: 'result-1',
    error_message: 'TimeoutError: locator.click: Timeout 15000ms exceeded.',
    heal_blocked_reason: null,
    heal_in_progress: true,
  }

  it('shows Healing… and a pulsing Self-healing status for an automatic heal', async () => {
    stubRunDetail([{ ...healingResult, heal_kind: 'automatic', auto_heal_attempt_count: 1 }])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const chip = await screen.findByText('Healing…')
    expect(chip.closest('span[title]')).toHaveAttribute(
      'title',
      'Self-healing in progress — automatic attempt 2 of 2',
    )
    expect(screen.getByText('Self-healing')).toBeInTheDocument()
    expect(screen.queryByTitle('Retry this test with self-healing')).toBeNull()
    expect(screen.queryByRole('button', { name: /Retry with self-healing unavailable/ })).toBeNull()
  })

  it('says manual in the tooltip for a Retry heal, even after a reload', async () => {
    stubRunDetail([{ ...healingResult, heal_kind: 'manual', manual_heal_attempt_count: 1 }])

    // A fresh mount stands in for a reload / another tab: no local state.
    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const chip = await screen.findByText('Healing…')
    expect(chip.closest('span[title]')).toHaveAttribute(
      'title',
      'Self-healing in progress — manual remediation attempt 2 of 3',
    )
  })

  it('hides the Retry-unavailable and Exhausted chips while a heal is in progress', async () => {
    stubRunDetail([
      { ...healingResult, id: 'result-1', heal_kind: 'automatic', heal_blocked_reason: "Assertion failures aren't self-healed." },
      { ...healingResult, id: 'result-2', heal_kind: 'manual', manual_heal_attempt_count: 3 },
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findAllByText('Healing…')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /Retry with self-healing unavailable/ })).toBeNull()
    expect(screen.queryByText('Heal exhausted')).toBeNull()
  })

  it('shows Failed and Retry as before when no heal is in progress', async () => {
    stubRunDetail([{ ...healingResult, heal_in_progress: false, heal_kind: null }])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findByTitle('Retry this test with self-healing')).toBeEnabled()
    expect(screen.queryByText('Healing…')).toBeNull()
    expect(screen.queryByText('Self-healing')).toBeNull()
  })

  it('keeps Healing… after Retry until the server says the heal has ended', async () => {
    const server = { healInProgress: false }
    const run = {
      id: 'run-1',
      run_number: 3,
      name: '#3 - Full Suite Run',
      status: 'completed',
      trigger: 'Manual run',
      pass_rate: 0,
      health: { tier: 'failing', headline: 'Failing' },
      total_count: 1,
      passed_count: 0,
      failed_count: 1,
      timed_out_count: 0,
      errored_count: 0,
      blocked_count: 0,
      blocked_reason: null,
      environment_snapshot: 'staging',
      target_base_url_snapshot: 'https://x.example.com',
      created_at: '2026-09-01T00:00:00Z',
      started_at: null,
      completed_at: null,
      allure_report_available: false,
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST' && url.endsWith('/test-results/result-1/heal')) {
          return { ok: true, status: 202, json: async () => ({ started: true }) }
        }
        if (url.includes('/test-runs/run-1')) {
          const result = {
            ...healingResult,
            heal_in_progress: server.healInProgress,
            heal_kind: server.healInProgress ? 'manual' : null,
          }
          return { ok: true, status: 200, json: async () => ({ ...run, results: [result] }) }
        }
        if (url.includes('/test-runs')) {
          return { ok: true, status: 200, json: async () => ({ items: [run], next_cursor: null }) }
        }
        return { ok: true, status: 200, json: async () => ({ available: true }) }
      }),
    )

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)
    ;(await screen.findByTitle('Retry this test with self-healing')).click()
    await screen.findByText('Healing…')

    // Claim taken, heal running for a few polls — the label holds.
    server.healInProgress = true
    await new Promise((resolve) => setTimeout(resolve, 3500))
    expect(screen.getByText('Healing…')).toBeInTheDocument()

    // Server says it ended — the label clears.
    server.healInProgress = false
    await waitFor(() => expect(screen.queryByText('Healing…')).toBeNull(), { timeout: 5000 })
    expect(await screen.findByTitle('Retry this test with self-healing')).toBeInTheDocument()
  }, 15000)
})
