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
        code: 'def test_guest_checkout():\n    pass\n',
      },
      {
        id: 'case-2',
        name: 'Checkout with expired card',
        type: 'negative',
        code: 'def test_expired_card():\n    pass\n',
      },
    ],
  },
]

const SCENARIOS = [
  { id: 's1', journey_id: 'journey-1' },
  { id: 's2', journey_id: 'journey-1' },
]

function stubFetch(overrides: { suites?: typeof SUITES; scenarios?: unknown[] } = {}) {
  const { suites = SUITES, scenarios = SCENARIOS } = overrides
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('/test-suites')) {
        return { ok: true, status: 200, json: async () => suites }
      }
      if (url.includes('/scenarios')) {
        return { ok: true, status: 200, json: async () => scenarios }
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
    render(<TestSuiteResults applicationId="app-1" onGoToDashboard={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('Generating')
    })
    expect(screen.getByRole('status').textContent).toContain('0/2')
  })

  it('shows the completed summary, stats, and reveals per-suite details by default', async () => {
    stubFetch()
    render(<TestSuiteResults applicationId="app-1" onGoToDashboard={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText(/Generated 2 test cases across 1 journeys/)).toBeTruthy()
    })
    expect(screen.getByText('checkout.spec.ts')).toBeTruthy()
    expect(screen.getByText('Guest checkout')).toBeTruthy()
    expect(screen.getByText('Happy Path')).toBeTruthy()
    expect(screen.getByText('Negative Path')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: 'View Code' })).toHaveLength(2)
  })

  it('toggles test details visibility', async () => {
    stubFetch()
    render(<TestSuiteResults applicationId="app-1" onGoToDashboard={() => {}} />)

    await waitFor(() => screen.getByText('Guest checkout'))

    fireEvent.click(screen.getByRole('button', { name: /Hide test details/ }))
    expect(screen.queryByText('Guest checkout')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Show test details/ }))
    expect(screen.getByText('Guest checkout')).toBeTruthy()
  })

  it('calls onGoToDashboard when the Go to Dashboard button is clicked', async () => {
    stubFetch()
    const onGoToDashboard = vi.fn()
    render(<TestSuiteResults applicationId="app-1" onGoToDashboard={onGoToDashboard} />)

    const button = await screen.findByRole('button', { name: 'Go to Dashboard →' })
    fireEvent.click(button)

    expect(onGoToDashboard).toHaveBeenCalledOnce()
  })

  it('clicking View Code opens a modal with that row\'s own code; a different row shows its own code', async () => {
    stubFetch()
    render(<TestSuiteResults applicationId="app-1" onGoToDashboard={() => {}} />)

    await waitFor(() => screen.getByText('Guest checkout'))

    const codeButtons = screen.getAllByRole('button', { name: 'View Code' })
    fireEvent.click(codeButtons[0])
    expect(screen.getByText(/test_guest_checkout/)).toBeTruthy()

    fireEvent.click(screen.getByLabelText('Close'))
    fireEvent.click(codeButtons[1])
    expect(screen.getByText(/test_expired_card/)).toBeTruthy()
  })
})
