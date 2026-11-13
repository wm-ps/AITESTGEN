import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RunsTab } from './RunsTab'

afterEach(() => {
  vi.unstubAllGlobals()
})

const baseResult = {
  journey_name: 'Claims',
  stack_trace: null,
  blocked_reason: null,
  auto_heal_attempt_count: 0,
  manual_heal_attempt_count: 0,
  healed_test_asset_id: null,
  auto_heal_attempt_cap: 2,
  max_heal_attempts: 3,
  heal_blocked_reason: null,
  error_message: null,
  duration_ms: 1000,
}

// A result of one test on one browser. `test` picks which test it is.
let nextId = 0
function result(test: 'claim' | 'login', browser: string, status: string, extra: Record<string, unknown> = {}) {
  nextId += 1
  return {
    ...baseResult,
    id: `result-${nextId}`,
    scenario_id: `scenario-${test}`,
    scenario_name: test === 'claim' ? 'Submits a claim' : 'Signs in',
    test_case_number: test === 'claim' ? 7 : 8,
    browser,
    status,
    ...extra,
  }
}

const LOCATOR_FAILURE = 'TimeoutError: locator.click: Timeout 15000ms exceeded.'

function stub(runOverrides: Record<string, unknown>, results: Array<Record<string, unknown>>) {
  const run = {
    id: 'run-1',
    run_number: 3,
    name: '#3 - Full Suite Run',
    status: 'completed',
    trigger: 'Manual run',
    pass_rate: 0.5,
    health: { tier: 'critical', headline: 'Critical' },
    // What runs counted before per-test counters: one per result, so the screen must not trust it.
    total_count: results.length,
    passed_count: results.filter((r) => r.status === 'passed').length,
    failed_count: results.filter((r) => r.status === 'failed').length,
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
    ...runOverrides,
  }
  const artifactRequests: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('/artifacts')) {
        artifactRequests.push(url)
        return { ok: true, status: 200, json: async () => [] }
      }
      if (url.includes('/test-runs/run-1')) {
        return { ok: true, status: 200, json: async () => ({ ...run, results }) }
      }
      if (url.includes('/test-runs')) {
        return { ok: true, status: 200, json: async () => ({ items: [run], next_cursor: null }) }
      }
      return { ok: true, status: 200, json: async () => ({ available: true }) }
    }),
  )
  return { artifactRequests }
}

const MULTI = { browsers: ['chromium', 'firefox'], viewport_width: 1920, viewport_height: 1080 }

describe('RunsTab on several browsers', () => {
  it('shows one row per test, not one per browser', async () => {
    stub(MULTI, [
      result('claim', 'chromium', 'passed'),
      result('claim', 'firefox', 'passed'),
      result('login', 'chromium', 'passed'),
      result('login', 'firefox', 'passed'),
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findByText(/Submits a claim/)).toBeInTheDocument()
    expect(screen.getAllByText(/Submits a claim/)).toHaveLength(1)
    expect(screen.getAllByText(/Signs in/)).toHaveLength(1)
    // A chip per browser for each test.
    expect(screen.getAllByRole('img', { name: /Chrome - 1920 × 1080/ })).toHaveLength(2)
    expect(screen.getAllByRole('img', { name: /Firefox - 1920 × 1080/ })).toHaveLength(2)
  })

  it('says the browser and size when hovering a chip, and how it went', async () => {
    stub(MULTI, [result('claim', 'chromium', 'passed'), result('claim', 'firefox', 'failed', { error_message: 'boom' })])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const chrome = await screen.findByRole('img', { name: 'Chrome - 1920 × 1080 · Passed' })
    expect(chrome).toHaveAttribute('title', 'Chrome - 1920 × 1080 · Passed')
    expect(screen.getByRole('img', { name: 'Firefox - 1920 × 1080 · Failed' })).toBeInTheDocument()
  })

  it('names the browser a test failed on when Chrome passed it', async () => {
    stub(MULTI, [result('claim', 'chromium', 'passed'), result('claim', 'firefox', 'failed', { error_message: 'boom' })])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findByText('Fails only on Firefox')).toBeInTheDocument()
  })

  it('reads the row as failed if any browser failed', async () => {
    stub(MULTI, [result('claim', 'chromium', 'passed'), result('claim', 'firefox', 'failed', { error_message: 'boom' })])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const row = (await screen.findByText(/Submits a claim/)).closest('[role="button"]') as HTMLElement
    // No separate row pill: each browser's chip is the status.
    expect(within(row).getAllByText('Failed')).toHaveLength(1)
    expect(within(row).getAllByText('Passed')).toHaveLength(1)
  })

  it('opens one tab per browser, with the failed browser selected', async () => {
    const { artifactRequests } = stub(MULTI, [
      result('claim', 'chromium', 'passed'),
      result('claim', 'firefox', 'failed', { error_message: 'Firefox-only boom' }),
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)
    fireEvent.click((await screen.findByText(/Submits a claim/)).closest('[role="button"]') as HTMLElement)

    const chromeTab = screen.getByRole('tab', { name: 'Chrome - 1920 × 1080' })
    const firefoxTab = screen.getByRole('tab', { name: 'Firefox - 1920 × 1080' })
    expect(chromeTab).toHaveAttribute('aria-selected', 'false')
    expect(firefoxTab).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('Firefox-only boom')).toBeInTheDocument()
    expect(screen.queryByText('Passed cleanly')).not.toBeInTheDocument()
    // Only the selected tab loaded its screenshot and trace.
    await waitFor(() => expect(artifactRequests).toHaveLength(1))

    fireEvent.click(chromeTab)
    expect(await screen.findByText('Passed cleanly')).toBeInTheDocument()
    await waitFor(() => expect(artifactRequests).toHaveLength(2))
  })

  it('offers Retry with self-healing only on the Chrome tab', async () => {
    stub(MULTI, [
      result('claim', 'chromium', 'failed', { error_message: LOCATOR_FAILURE }),
      result('claim', 'firefox', 'failed', { error_message: LOCATOR_FAILURE }),
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)
    fireEvent.click((await screen.findByText(/Submits a claim/)).closest('[role="button"]') as HTMLElement)

    // Both failed, so the first (Chrome) tab is selected.
    expect(await screen.findByTitle('Retry this test with self-healing')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Firefox - 1920 × 1080' }))
    await screen.findByRole('tabpanel')
    expect(screen.queryByTitle('Retry this test with self-healing')).not.toBeInTheDocument()
  })

  it('shows one quiet line for the tests and browsers on the Total tile', async () => {
    stub(MULTI, [
      result('claim', 'chromium', 'passed'),
      result('claim', 'firefox', 'passed'),
      result('login', 'chromium', 'passed'),
      result('login', 'firefox', 'passed'),
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const note = await screen.findByText('ran in 2 browsers')
    // 2 tests, not the 4 results.
    expect(note.parentElement).toHaveTextContent(/Total\s*2/)
  })

  it('shows the result split as tests, not as results', async () => {
    stub(MULTI, [
      result('claim', 'chromium', 'passed'),
      result('claim', 'firefox', 'passed'),
      result('login', 'chromium', 'passed'),
      result('login', 'firefox', 'failed'),
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    // 1 of 2 tests passed; dividing by the 4 results would read 25%.
    expect(await screen.findByText('50%')).toBeInTheDocument()
  })

  it('gives the browsers their own results card next to the result split', async () => {
    stub(MULTI, [
      result('claim', 'chromium', 'passed'),
      result('claim', 'firefox', 'passed'),
      result('login', 'chromium', 'passed'),
      result('login', 'firefox', 'failed'),
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const card = (await screen.findByText('Results by browser')).parentElement as HTMLElement
    expect(screen.getByText('Result split')).toBeInTheDocument()
    // The counts show on hover, not as text beside the bars.
    expect(within(card).queryByRole('tooltip')).not.toBeInTheDocument()
    const row = within(card).getByText('Firefox').parentElement as HTMLElement
    fireEvent.mouseEnter(row.children[1])
    const tip = within(card).getByRole('tooltip')
    expect(tip).toHaveTextContent('2 test cases')
    expect(tip).toHaveTextContent('1 Passed')
    expect(tip).toHaveTextContent('1 Failed')
  })

  it('lists the tests that differ by browser and filters to them from its tile', async () => {
    stub(MULTI, [
      result('claim', 'chromium', 'passed'),
      result('claim', 'firefox', 'failed', { error_message: 'boom' }),
      result('login', 'chromium', 'passed'),
      result('login', 'firefox', 'passed'),
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    const tile = await screen.findByRole('button', { name: /Browser differences/ })
    expect(tile).toHaveTextContent('1')
    expect(screen.getByText(/Signs in/)).toBeInTheDocument()

    fireEvent.click(tile)

    await waitFor(() => expect(screen.queryByText(/Signs in/)).not.toBeInTheDocument())
    expect(screen.getByText(/Submits a claim/)).toBeInTheDocument()
  })

  it('has no differences tile when every browser agreed', async () => {
    stub(MULTI, [result('claim', 'chromium', 'passed'), result('claim', 'firefox', 'passed')])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    await screen.findByText(/Submits a claim/)
    expect(screen.queryByText('Browser differences')).not.toBeInTheDocument()
  })

  it('says what the run used in its header', async () => {
    stub(MULTI, [result('claim', 'chromium', 'passed'), result('claim', 'firefox', 'passed')])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findByText(/staging · 2 browsers · 1920 × 1080/)).toBeInTheDocument()
  })
})

describe('RunsTab on one browser', () => {
  it('looks exactly as it did: no chips, no sections, no extra tiles or line', async () => {
    stub({}, [
      result('claim', 'chromium', 'failed', { error_message: LOCATOR_FAILURE }),
      result('login', 'chromium', 'passed'),
    ])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    fireEvent.click((await screen.findByText(/Submits a claim/)).closest('[role="button"]') as HTMLElement)

    expect(screen.queryByRole('img', { name: /Chrome -/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/Fails only on/)).not.toBeInTheDocument()
    expect(screen.queryByText('Browser differences')).not.toBeInTheDocument()
    expect(screen.queryByText(/browsers$/)).not.toBeInTheDocument()
    expect(screen.queryByText('Results by browser')).not.toBeInTheDocument()
    // The retry chip and the failure are where they always were.
    expect(screen.getByTitle('Retry this test with self-healing')).toBeInTheDocument()
    expect(await screen.findByText(LOCATOR_FAILURE)).toBeInTheDocument()
  })

  it('treats results from before browsers existed as Chrome', async () => {
    const { browser: _browser, ...old } = result('claim', 'chromium', 'passed')
    stub({}, [old])

    render(<RunsTab applicationId="app-1" initialRunId="run-1" />)

    expect(await screen.findByText(/Submits a claim/)).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /Chrome -/ })).not.toBeInTheDocument()
  })

  it('says nothing about browsers in the run list for a default run', async () => {
    stub({}, [result('claim', 'chromium', 'passed')])

    render(<RunsTab applicationId="app-1" />)

    await screen.findByText('Run #3')
    expect(screen.queryByText(/1280 × 720/)).not.toBeInTheDocument()
  })

  it('names the browsers and size a run used in the run list', async () => {
    stub(MULTI, [result('claim', 'chromium', 'passed'), result('claim', 'firefox', 'passed')])

    render(<RunsTab applicationId="app-1" />)

    const pill = await screen.findByText('2 browsers · 1920 × 1080')
    expect(pill).toHaveAttribute('title', 'Chrome - 1920 × 1080, Firefox - 1920 × 1080')
  })
})
