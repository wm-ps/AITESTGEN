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

// Every Journey referenced by a given Scenario is treated as "covered" —
// isComplete (journeysCovered >= journeys.length) needs a matching /journeys
// response, not just /scenarios, or the Review screen never leaves the
// "still generating" loader.
function stubFetch(
  scenarios: (typeof INCOMPLETE_SCENARIO)[],
  overrides: { onTestDataUpdate?: (body: unknown) => void } = {},
) {
  const journeys = [...new Set(scenarios.map((s) => s.journey_id))].map((id) => ({
    id,
    name: scenarios.find((s) => s.journey_id === id)!.journey_name,
    step_count: 1,
  }))
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
      if (url.includes('/journeys')) {
        return { ok: true, status: 200, json: async () => journeys }
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
    render(<ReviewScenarios furthestCount={2}applicationId="app-1" onContinueToGenerate={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('Guest checkout')).toBeTruthy()
    })
    expect(screen.getByText('from Checkout')).toBeTruthy()
    expect(screen.getByText('Happy Path')).toBeTruthy()
  })

  it('shows a Test Data Required readiness pill but leaves Continue enabled — blank fields get a default at generation time', async () => {
    stubFetch([INCOMPLETE_SCENARIO])
    render(<ReviewScenarios furthestCount={2}applicationId="app-1" onContinueToGenerate={() => {}} />)

    await waitFor(() => screen.getByText('Guest checkout'))
    expect(screen.getAllByText('Test Data Required').length).toBeGreaterThan(0)
    const button = screen.getByRole('button', {
      name: 'Generate Test Suite →',
    }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
  })

  it('enables Continue to Generate Test Suite once every scenario is complete', async () => {
    stubFetch([COMPLETE_SCENARIO])
    render(<ReviewScenarios furthestCount={2}applicationId="app-1" onContinueToGenerate={() => {}} />)

    await waitFor(() => screen.getByText('Checkout with promo'))
    const button = screen.getByRole('button', {
      name: 'Generate Test Suite →',
    }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
  })

  it('keeps Continue disabled only when there are zero scenarios', async () => {
    stubFetch([])
    render(<ReviewScenarios furthestCount={2}applicationId="app-1" onContinueToGenerate={() => {}} />)

    await waitFor(() => screen.getByText('Generating scenarios'))
    const button = screen.getByRole('button', {
      name: 'Generate Test Suite →',
    }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
  })

  it('selecting a scenario shows its steps, test data inputs, and expected result', async () => {
    stubFetch([INCOMPLETE_SCENARIO])
    render(<ReviewScenarios furthestCount={2}applicationId="app-1" onContinueToGenerate={() => {}} />)

    await waitFor(() => screen.getByText('Guest checkout'))
    fireEvent.click(screen.getByText('Guest checkout'))

    await waitFor(() => {
      expect(screen.getByText('Add item to cart')).toBeTruthy()
    })
    expect(screen.getByText('Order confirmation is shown')).toBeTruthy()
    expect(screen.getByLabelText(/^username/)).toBeTruthy()
    expect(screen.getAllByText('Happy Path').length).toBeGreaterThan(0)
  })

  it('saves a test data value on blur', async () => {
    let updatedWith: unknown
    stubFetch([INCOMPLETE_SCENARIO], {
      onTestDataUpdate: (body) => {
        updatedWith = body
      },
    })
    render(<ReviewScenarios furthestCount={2}applicationId="app-1" onContinueToGenerate={() => {}} />)

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

  it('clicking Continue to Generate Test Suite calls onContinueToGenerate', async () => {
    stubFetch([COMPLETE_SCENARIO])
    const onContinueToGenerate = vi.fn()
    render(
      <ReviewScenarios furthestCount={2}applicationId="app-1" onContinueToGenerate={onContinueToGenerate} />,
    )

    await waitFor(() => screen.getByText('Checkout with promo'))
    fireEvent.click(screen.getByRole('button', { name: 'Generate Test Suite →' }))
    expect(onContinueToGenerate).toHaveBeenCalledOnce()
  })

  it('shows the shared generation-loader animation, not the scenario list, while scenarios are still generating', async () => {
    stubFetch([])
    render(<ReviewScenarios furthestCount={2}applicationId="app-1" onContinueToGenerate={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('Generating scenarios')
    })
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('keeps showing the loader — not a partial list — once some Scenarios have landed but their Journeys are not all covered yet', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/journeys')) {
          // Two Journeys exist, but only one has a Scenario so far.
          return {
            ok: true,
            status: 200,
            json: async () => [
              { id: 'journey-1', name: 'Checkout', step_count: 1 },
              { id: 'journey-2', name: 'Returns', step_count: 1 },
            ],
          }
        }
        if (url.includes('/scenarios')) {
          return { ok: true, status: 200, json: async () => [INCOMPLETE_SCENARIO] }
        }
        return { ok: true, status: 200, json: async () => [] }
      }),
    )
    render(<ReviewScenarios furthestCount={2}applicationId="app-1" onContinueToGenerate={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('Generating scenarios')
    })
    expect(screen.queryByText('Guest checkout')).toBeNull()
  })
})
