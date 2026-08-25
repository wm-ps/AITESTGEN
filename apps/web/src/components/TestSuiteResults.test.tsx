import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TestSuiteResults } from './TestSuiteResults'

const SUITES = [
  {
    id: 'suite-1',
    name: 'Checkout Test Suite',
    journey_name: 'Checkout',
    test_cases: [
      {
        id: 'case-1',
        name: 'Guest checkout',
        type: 'happy',
        code: "import { test, expect } from '@playwright/test'\n\ntest('test_guest_checkout', async ({ page }) => {})\n",
      },
      {
        id: 'case-2',
        name: 'Checkout with expired card',
        type: 'negative',
        code: "import { test, expect } from '@playwright/test'\n\ntest('test_expired_card', async ({ page }) => {})\n",
      },
    ],
  },
]

const SCENARIOS = [
  { id: 's1', journey_id: 'journey-1' },
  { id: 's2', journey_id: 'journey-1' },
]

function stubFetch(
  overrides: {
    suites?: ((typeof SUITES)[number] & { status?: string })[]
    scenarios?: unknown[]
    download?: { ok: boolean; status?: number }
  } = {},
) {
  const { suites = SUITES, scenarios = SCENARIOS, download = { ok: true } } = overrides
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('/test-suites/download')) {
        if (!download.ok) {
          return {
            ok: false,
            status: download.status ?? 500,
            json: async () => ({ detail: 'export failed' }),
          }
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Disposition': 'attachment; filename="acme-tests.zip"' }),
          blob: async () => new Blob(['zip-bytes']),
        }
      }
      if (url.includes('/test-suites')) {
        return { ok: true, status: 200, json: async () => suites }
      }
      if (url.includes('/scenarios')) {
        return { ok: true, status: 200, json: async () => scenarios }
      }
      if (url.includes('/journeys')) {
        const journeyIds = [...new Set((scenarios as { journey_id: string }[]).map((s) => s.journey_id))]
        return { ok: true, status: 200, json: async () => journeyIds.map((id) => ({ id })) }
      }
      if (url.includes('/generation-status')) {
        return { ok: true, status: 200, json: async () => ({ available: true }) }
      }
      return { ok: true, status: 200, json: async () => [] }
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('TestSuiteResults', () => {
  it('shows a spinner and live progress while generation is still in flight', async () => {
    stubFetch({ suites: [], scenarios: SCENARIOS })
    render(<TestSuiteResults furthestCount={4}applicationId="app-1" onRunTests={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('Generating')
    })
    expect(screen.getByRole('status').textContent).toContain('0/2')
  })

  it('leaves the loader once a suite is permanently incomplete, instead of waiting forever for a test-case count that will never arrive', async () => {
    // SuiteGenerationWorkflow gives up on a Scenario after its wave retries
    // and writes the suite terminal ("incomplete") — that Scenario's
    // TestAsset never lands, so a testCaseCount >= expectedTestCaseCount
    // gate would spin on the loader forever even though nothing more is
    // ever going to happen.
    stubFetch({
      suites: [{ ...SUITES[0], status: 'incomplete', test_cases: [SUITES[0].test_cases[0]] }],
      scenarios: SCENARIOS,
    })
    render(<TestSuiteResults furthestCount={4}applicationId="app-1" onRunTests={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText(/Generated 1 test cases across 1 journeys/)).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: /View Tests/ }))
    expect(screen.getByText('Incomplete')).toBeTruthy()
  })

  it('retries only the failed suite when Generate is clicked, and the loader reappears', async () => {
    let suites = [{ ...SUITES[0], status: 'incomplete', test_cases: [SUITES[0].test_cases[0]] }]
    const fetchMock = vi.fn(async (url: string, _opts?: RequestInit) => {
      if (url.includes('/generate-suite')) {
        suites = [{ ...SUITES[0], status: 'generating', test_cases: [SUITES[0].test_cases[0]] }]
        return { ok: true, status: 202, json: async () => ({ suites_triggered: 1 }) }
      }
      if (url.includes('/test-suites')) {
        return { ok: true, status: 200, json: async () => suites }
      }
      if (url.includes('/scenarios')) {
        return { ok: true, status: 200, json: async () => SCENARIOS }
      }
      if (url.includes('/journeys')) {
        return { ok: true, status: 200, json: async () => [{ id: 'journey-1' }] }
      }
      if (url.includes('/generation-status')) {
        return { ok: true, status: 200, json: async () => ({ available: true }) }
      }
      return { ok: true, status: 200, json: async () => [] }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<TestSuiteResults furthestCount={4} applicationId="app-1" onRunTests={() => {}} />)

    expect(await screen.findByText(/failed to generate\./)).toBeTruthy()
    const retryButton = screen.getByRole('button', { name: /^Retry Generation$/ })
    fireEvent.click(retryButton)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/generate-suite'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('Generating')
    })
  })

  it('shows the completed summary and stats, with the file list and its scenarios collapsed by default', async () => {
    stubFetch()
    render(<TestSuiteResults furthestCount={4}applicationId="app-1" onRunTests={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText(/Generated 2 test cases across 1 journeys/)).toBeTruthy()
    })
    expect(screen.getByText('Generated Tests')).toBeTruthy()
    expect(screen.getByText('2 tests across 1 file')).toBeTruthy()
    expect(screen.queryByText('checkout.spec.ts')).toBeNull()
    expect(screen.queryByText('Guest checkout')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /View Tests/ }))
    expect(screen.getByText('checkout.spec.ts')).toBeTruthy()
    expect(screen.queryByText('Guest checkout')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /checkout\.spec\.ts/ }))
    expect(screen.getByText('Guest checkout')).toBeTruthy()
    expect(screen.getByText('Happy Path')).toBeTruthy()
    expect(screen.getByText('Negative Path')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: 'Code' })).toHaveLength(2)
  })

  it('toggles test details visibility', async () => {
    stubFetch()
    render(<TestSuiteResults furthestCount={4}applicationId="app-1" onRunTests={() => {}} />)

    await waitFor(() => screen.getByText(/Generated 2 test cases across 1 journeys/))

    fireEvent.click(screen.getByRole('button', { name: /View Tests/ }))
    fireEvent.click(screen.getByRole('button', { name: /checkout\.spec\.ts/ }))
    expect(screen.getByText('Guest checkout')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Hide Tests/ }))
    expect(screen.queryByText('Guest checkout')).toBeNull()
    expect(screen.queryByText('checkout.spec.ts')).toBeNull()
  })

  it('calls onRunTests when the Run Tests button is clicked', async () => {
    stubFetch()
    const onRunTests = vi.fn()
    render(<TestSuiteResults furthestCount={4} applicationId="app-1" onRunTests={onRunTests} />)

    const button = await screen.findByRole('button', { name: 'Run Tests' })
    fireEvent.click(button)

    expect(onRunTests).toHaveBeenCalledOnce()
  })

  it('clicking View Code opens a modal with that row\'s own code; a different row shows its own code', async () => {
    stubFetch()
    render(<TestSuiteResults furthestCount={4}applicationId="app-1" onRunTests={() => {}} />)

    await waitFor(() => screen.getByRole('button', { name: /View Tests/ }))
    fireEvent.click(screen.getByRole('button', { name: /View Tests/ }))
    fireEvent.click(screen.getByRole('button', { name: /checkout\.spec\.ts/ }))
    await waitFor(() => screen.getByText('Guest checkout'))

    const codeButtons = screen.getAllByRole('button', { name: 'Code' })
    fireEvent.click(codeButtons[0])
    expect(screen.getByText(/test_guest_checkout/)).toBeTruthy()

    fireEvent.click(screen.getByLabelText('Close'))
    fireEvent.click(codeButtons[1])
    expect(screen.getByText(/test_expired_card/)).toBeTruthy()
  })

  it('downloads the test suite project when Download Test Suite is clicked', async () => {
    stubFetch()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:mock-url'),
      revokeObjectURL: vi.fn(),
    })
    render(<TestSuiteResults furthestCount={4}applicationId="app-1" onRunTests={() => {}} />)

    const button = (await screen.findByRole('button', {
      name: /Download Test Suite/,
    })) as HTMLButtonElement
    expect(button.disabled).toBe(false)

    fireEvent.click(button)
    await waitFor(() => expect(screen.getByRole('button', { name: /Downloading/ })).toBeTruthy())
    await waitFor(() => {
      const settled = screen.getByRole('button', { name: /Download Test Suite/ }) as HTMLButtonElement
      expect(settled.disabled).toBe(false)
    })
    expect(URL.createObjectURL).toHaveBeenCalledOnce()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
  })

  it('re-enables the Download button after a failed export', async () => {
    stubFetch({ download: { ok: false, status: 500 } })
    render(<TestSuiteResults furthestCount={4}applicationId="app-1" onRunTests={() => {}} />)

    const button = await screen.findByRole('button', { name: /Download Test Suite/ })
    fireEvent.click(button)

    await waitFor(() => {
      const settled = screen.getByRole('button', { name: /Download Test Suite/ }) as HTMLButtonElement
      expect(settled.disabled).toBe(false)
    })
  })
})
