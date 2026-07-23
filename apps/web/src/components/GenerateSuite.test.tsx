import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GenerateSuite } from './GenerateSuite'

const JOURNEYS = [
  { id: 'journey-1', name: 'Checkout', description: null, step_count: 3 },
  { id: 'journey-2', name: 'Sign up', description: null, step_count: 2 },
]

const SCENARIOS = [
  {
    id: 'scenario-1',
    journey_id: 'journey-1',
    journey_name: 'Checkout',
    type: 'happy',
    name: 'Guest checkout',
    steps: [],
    expected_result: '',
    test_data: [],
    test_data_complete: true,
  },
  {
    id: 'scenario-2',
    journey_id: 'journey-1',
    journey_name: 'Checkout',
    type: 'negative',
    name: 'Checkout with expired card',
    steps: [],
    expected_result: '',
    test_data: [],
    test_data_complete: true,
  },
]

function stubFetch(overrides: { onGenerate?: () => void } = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.includes('/generate-suite')) {
        overrides.onGenerate?.()
        return { ok: true, status: 202, json: async () => ({ suites_triggered: 1 }) }
      }
      if (url.includes('/journeys')) {
        return { ok: true, status: 200, json: async () => JOURNEYS }
      }
      if (url.includes('/scenarios')) {
        return { ok: true, status: 200, json: async () => SCENARIOS }
      }
      return { ok: true, status: 200, json: async () => [] }
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('GenerateSuite', () => {
  it('summarizes suite count (journeys with current scenarios) and total test case count', async () => {
    stubFetch()
    render(<GenerateSuite applicationId="app-1" onGenerated={() => {}} />)

    // Only journey-1 has scenarios — journey-2 (no scenarios) doesn't count
    // toward the suite total, matching Task 3's "only Journeys with current
    // Scenarios get a TestSuite" rule.
    await waitFor(() => {
      expect(screen.getByText('1')).toBeTruthy()
    })
    expect(screen.getByText('2')).toBeTruthy()
    expect(screen.getByText('Test Suite')).toBeTruthy()
    expect(screen.getByText('Test Cases')).toBeTruthy()
  })

  it('has no suite-name input field — naming is automatic (AC 2)', async () => {
    stubFetch()
    render(<GenerateSuite applicationId="app-1" onGenerated={() => {}} />)
    await waitFor(() => screen.getByText('Test Suite'))
    expect(screen.queryByLabelText(/suite name/i)).toBeNull()
  })

  it('renders the Execution placeholder as inert radio controls', async () => {
    stubFetch()
    render(<GenerateSuite applicationId="app-1" onGenerated={() => {}} />)
    await waitFor(() => screen.getByText('Test Suite'))
    expect(screen.getByLabelText('Run immediately')).toBeTruthy()
    expect(screen.getByLabelText('Schedule for later')).toBeTruthy()
    expect(screen.getByLabelText('Save without running')).toBeTruthy()
  })

  it('clicking Generate Test Suite triggers the endpoint and calls onGenerated', async () => {
    const onGenerate = vi.fn()
    stubFetch({ onGenerate })
    const onGenerated = vi.fn()
    render(<GenerateSuite applicationId="app-1" onGenerated={onGenerated} />)

    await waitFor(() => screen.getByText('Test Suite'))
    fireEvent.click(screen.getByRole('button', { name: 'Generate Test Suite' }))

    await waitFor(() => {
      expect(onGenerate).toHaveBeenCalledOnce()
      expect(onGenerated).toHaveBeenCalledOnce()
    })
  })
})
