import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  // Buckets are exclusive and ranked Self-healed > Flaky > Passed/Failed, so
  // a healed result that is also flaky counts only as Self-healed, and the
  // four tiles always add up to the finished results.
  it('splits results into Passed / Self-healed / Flaky / Failed by priority', async () => {
    const base = { ...failedResult, error_message: null, heal_blocked_reason: null }
    stubRunDetail([
      { ...base, id: 'r1', scenario_name: 'Clean pass', status: 'passed' },
      { ...base, id: 'r2', scenario_name: 'Healed pass', status: 'passed', healed_test_asset_id: 'asset-2' },
      { ...base, id: 'r3', scenario_name: 'Healed and flaky', status: 'passed', healed_test_asset_id: 'asset-3', is_flaky: true },
      { ...base, id: 'r4', scenario_name: 'Flaky pass', status: 'passed', is_flaky: true },
      { ...base, id: 'r5', scenario_name: 'Flaky fail', status: 'failed', is_flaky: true },
      { ...base, id: 'r6', scenario_name: 'Plain fail', status: 'failed' },
      { ...base, id: 'r7', scenario_name: 'Timed out', status: 'timed_out' },
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const tileValue = async (label: string) =>
      (await screen.findByText(label, { selector: 'div' })).nextElementSibling?.textContent
    await waitFor(async () => expect(await tileValue('Flaky')).toBe('2'))
    expect(await tileValue('Passed')).toBe('1')
    expect(await tileValue('Self-healed')).toBe('2')
    expect(await tileValue('Failed')).toBe('2')
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

  it('shows one pulsing Self-healing status (no separate Healing chip) for an automatic heal', async () => {
    stubRunDetail([{ ...healingResult, heal_kind: 'automatic', auto_heal_attempt_count: 1 }])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const chip = await screen.findByText('Self-healing')
    expect(chip.closest('div[title]')).toHaveAttribute(
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

    const chip = await screen.findByText('Self-healing')
    expect(chip.closest('div[title]')).toHaveAttribute(
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

    expect(await screen.findAllByText('Self-healing')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /Retry with self-healing unavailable/ })).toBeNull()
    expect(screen.queryByText('Heal exhausted')).toBeNull()
  })

  it('shows Failed and Retry as before when no heal is in progress', async () => {
    stubRunDetail([{ ...healingResult, heal_in_progress: false, heal_kind: null }])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findByTitle('Retry this test with self-healing')).toBeEnabled()
    expect(screen.queryByText('Self-healing')).toBeNull()
    expect(screen.queryByText('Self-healing')).toBeNull()
  })

  it('keeps Self-healing after Retry until the server says the heal has ended', async () => {
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
    await screen.findByText('Self-healing')

    // Claim taken, heal running for a few polls — the label holds.
    server.healInProgress = true
    await new Promise((resolve) => setTimeout(resolve, 3500))
    expect(screen.getByText('Self-healing')).toBeInTheDocument()

    // Server says it ended — the label clears.
    server.healInProgress = false
    await waitFor(() => expect(screen.queryByText('Self-healing')).toBeNull(), { timeout: 5000 })
    expect(await screen.findByTitle('Retry this test with self-healing')).toBeInTheDocument()
  }, 15000)

  // Plain-language failures: a Summary tab (default) and the untouched Raw
  // error tab, an "Explained by AI" caption only for AI explanations, and the
  // run-level root-cause banner.
  const RAW = "TimeoutError: locator.click: Timeout 15000ms exceeded.\nCall log:\n  - waiting for getByRole('button', { name: 'Submit' })"

  function stubExplainedRun(result: Record<string, unknown>, runExtras: Record<string, unknown> = {}) {
    const run = {
      id: 'run-1',
      run_number: 3,
      name: '#3 - Full Suite Run',
      status: 'completed',
      trigger: 'Manual run',
      pass_rate: 0,
      health: { tier: 'critical', headline: 'Failing' },
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
      ...runExtras,
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/artifacts')) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              { id: 'a1', artifact_type: 'screenshot', content_type: 'image/png', size_bytes: 2048, url: 'https://x/s.png' },
              { id: 'a2', artifact_type: 'trace', content_type: 'application/zip', size_bytes: 4096, url: 'https://x/t.zip' },
            ],
          }
        }
        if (url.includes('/test-runs/run-1')) {
          return { ok: true, status: 200, json: async () => ({ ...run, results: [{ ...failedResult, id: 'result-1', error_message: RAW, heal_blocked_reason: null, ...result }] }) }
        }
        if (url.includes('/test-runs')) {
          return { ok: true, status: 200, json: async () => ({ items: [run], next_cursor: null }) }
        }
        return { ok: true, status: 200, json: async () => ({ available: true }) }
      }),
    )
  }

  async function expandRow() {
    fireEvent.click(await screen.findByText(/Submits a claim/))
  }

  it('shows the plain Summary by default and the raw error on the Raw error tab', async () => {
    stubExplainedRun({
      failure_title: 'Couldn\'t click the "Submit" button',
      failure_detail: 'The test waited 15 seconds for the "Submit" button, but it never appeared.',
      failure_source: 'rules',
    })

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)
    await expandRow()

    expect(await screen.findByRole('tab', { name: 'Summary' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Couldn\'t click the "Submit" button')).toBeInTheDocument()
    expect(screen.queryByText(/TimeoutError: locator.click/)).toBeNull()
    expect(screen.queryByText('Explained by AI — may not be exact')).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: 'Raw error' }))
    expect(screen.getByText(/TimeoutError: locator.click/)).toBeInTheDocument()
    // Screenshot and trace are unchanged.
    expect(await screen.findByText(/Screenshot/)).toBeInTheDocument()
    expect(screen.getByText(/Playwright trace/)).toBeInTheDocument()
  })

  it('labels an AI explanation', async () => {
    stubExplainedRun({ failure_title: 'A widget failed', failure_detail: 'It likely crashed on save.', failure_source: 'ai' })

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)
    await expandRow()

    expect(await screen.findByText('A widget failed')).toBeInTheDocument()
    expect(screen.getByText('Explained by AI — may not be exact')).toBeInTheDocument()
  })

  it('shows just the raw error when there is no explanation', async () => {
    stubExplainedRun({})

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)
    await expandRow()

    expect(await screen.findByText(/TimeoutError: locator.click/)).toBeInTheDocument()
    expect(screen.queryByRole('tablist')).toBeNull()
  })

  it('shows the root-cause banner when most failures share one cause', async () => {
    stubExplainedRun(
      { failure_title: "Couldn't sign in to the app", failure_detail: '', failure_source: 'rules' },
      { root_cause: { title: "Vantage couldn't sign in to the app", affected: 38, total: 40 } },
    )

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findByText('38 of 40 failed tests have the same cause')).toBeInTheDocument()
    expect(screen.getByText("Vantage couldn't sign in to the app — fix this first.")).toBeInTheDocument()
  })
})
