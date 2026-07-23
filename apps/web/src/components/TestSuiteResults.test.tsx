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

function stubFetch(suites: typeof SUITES = SUITES) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('/test-suites')) {
        return { ok: true, status: 200, json: async () => suites }
      }
      return { ok: true, status: 200, json: async () => [] }
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('TestSuiteResults', () => {
  it('shows a suite-level summary before revealing details', async () => {
    stubFetch()
    render(<TestSuiteResults applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Test details →')).toBeTruthy()
    })
    expect(screen.queryByText('Checkout Test Suite')).toBeNull()
  })

  it('"Test details" reveals the per-suite breakdown with type badges and Code buttons', async () => {
    stubFetch()
    render(<TestSuiteResults applicationId="app-1" />)

    await waitFor(() => screen.getByText('Test details →'))
    fireEvent.click(screen.getByText('Test details →'))

    expect(screen.getByText('Checkout Test Suite')).toBeTruthy()
    expect(screen.getByText('Guest checkout')).toBeTruthy()
    expect(screen.getByText('Happy Path')).toBeTruthy()
    expect(screen.getByText('Negative Path')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: 'Code' })).toHaveLength(2)
  })

  it('clicking Code opens a modal with that row\'s own code; a different row shows its own code', async () => {
    stubFetch()
    render(<TestSuiteResults applicationId="app-1" />)

    await waitFor(() => screen.getByText('Test details →'))
    fireEvent.click(screen.getByText('Test details →'))

    const codeButtons = screen.getAllByRole('button', { name: 'Code' })
    fireEvent.click(codeButtons[0])
    expect(screen.getByText(/test_guest_checkout/)).toBeTruthy()

    fireEvent.click(screen.getByLabelText('Close'))
    fireEvent.click(codeButtons[1])
    expect(screen.getByText(/test_expired_card/)).toBeTruthy()
  })
})
