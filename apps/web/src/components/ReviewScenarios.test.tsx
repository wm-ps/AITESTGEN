import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewScenarios } from './ReviewScenarios'

const INCOMPLETE_SCENARIO = {
  id: 'scenario-1',
  journey_id: 'journey-1',
  journey_name: 'Checkout',
  type: 'happy',
  name: 'Guest checkout',
  steps: ['Add item to cart', 'Proceed to checkout', 'Submit payment'],
  expected_result: 'Order confirmation is shown',
  test_data: [
    { name: 'username', mandatory: true, value: null },
    { name: 'promo_code', mandatory: false, value: null },
  ],
  test_data_complete: false,
}

const COMPLETE_SCENARIO = {
  ...INCOMPLETE_SCENARIO,
  id: 'scenario-2',
  name: 'Checkout with promo',
  type: 'edge',
  test_data: [{ name: 'username', mandatory: true, value: 'qa-user' }],
  test_data_complete: true,
}

function stubFetch(
  scenarios: (typeof INCOMPLETE_SCENARIO)[],
  overrides: { onTestDataUpdate?: (body: unknown) => void } = {},
) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'PATCH' && url.includes('/test-data')) {
        const body = JSON.parse(init.body as string)
        overrides.onTestDataUpdate?.(body)
        const scenario = scenarios.find((s) => url.includes(s.id))
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ...scenario,
            test_data: scenario!.test_data.map((f) =>
              f.name === body.name ? { ...f, value: body.value } : f,
            ),
          }),
        }
      }
      if (init?.method === 'PATCH') {
        const body = JSON.parse(init.body as string)
        return { ok: true, status: 200, json: async () => ({ ...scenarios[0], name: body.name }) }
      }
      if (init?.method === 'DELETE') {
        return { ok: true, status: 204, json: async () => undefined }
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

describe('ReviewScenarios', () => {
  it('renders scenario rows with type badge and journey name', async () => {
    stubFetch([INCOMPLETE_SCENARIO])
    render(<ReviewScenarios applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText('Guest checkout')).toBeTruthy()
    })
    expect(screen.getByText('from Checkout')).toBeTruthy()
    expect(screen.getByText('Happy Path')).toBeTruthy()
  })

  it('shows an incomplete indicator and keeps Continue disabled while mandatory test data is empty', async () => {
    stubFetch([INCOMPLETE_SCENARIO])
    render(<ReviewScenarios applicationId="app-1" />)

    await waitFor(() => screen.getByText('Guest checkout'))
    expect(screen.getByText('Test data incomplete')).toBeTruthy()
    const button = screen.getByRole('button', {
      name: 'Continue to Generate Test Suite →',
    }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
  })

  it('enables Continue to Generate Test Suite once every scenario is complete', async () => {
    stubFetch([COMPLETE_SCENARIO])
    render(<ReviewScenarios applicationId="app-1" />)

    await waitFor(() => screen.getByText('Checkout with promo'))
    const button = screen.getByRole('button', {
      name: 'Continue to Generate Test Suite →',
    }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
  })

  it('selecting a scenario shows its steps, test data inputs, and expected result', async () => {
    stubFetch([INCOMPLETE_SCENARIO])
    render(<ReviewScenarios applicationId="app-1" />)

    await waitFor(() => screen.getByText('Guest checkout'))
    fireEvent.click(screen.getByText('Guest checkout'))

    await waitFor(() => {
      expect(screen.getByText('Add item to cart')).toBeTruthy()
    })
    expect(screen.getByText('Order confirmation is shown')).toBeTruthy()
    expect(screen.getByLabelText(/^username/)).toBeTruthy()
  })

  it('saves a test data value on blur', async () => {
    let updatedWith: unknown
    stubFetch([INCOMPLETE_SCENARIO], {
      onTestDataUpdate: (body) => {
        updatedWith = body
      },
    })
    render(<ReviewScenarios applicationId="app-1" />)

    await waitFor(() => screen.getByText('Guest checkout'))
    fireEvent.click(screen.getByText('Guest checkout'))
    await waitFor(() => screen.getByLabelText(/^username/))

    const input = screen.getByLabelText(/^username/)
    fireEvent.change(input, { target: { value: 'qa-user' } })
    fireEvent.blur(input)

    await waitFor(() => {
      expect(updatedWith).toEqual({ name: 'username', value: 'qa-user' })
    })
  })

  it('renders an empty state when there are no scenarios yet', async () => {
    stubFetch([])
    render(<ReviewScenarios applicationId="app-1" />)

    await waitFor(() => {
      expect(screen.getByText(/No Scenarios yet/)).toBeTruthy()
    })
  })
})
