import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DiscoverJourneys } from './DiscoverJourneys'

const JOURNEYS = [{ id: 'journey-1', name: 'Checkout', step_count: 2 }]
const STEPS = [
  { step_order: 1, stage_label: 'Login', route: 'https://app.example.com/login', method: 'GET' },
  {
    step_order: 2,
    stage_label: 'MFA Verification',
    route: 'https://app.example.com/mfa',
    method: 'GET',
  },
]

function stubFetch(overrides: {
  onRename?: (name: string) => void
  onDelete?: () => void
} = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'PATCH') {
        const body = JSON.parse(init.body as string)
        overrides.onRename?.(body.name)
        return { ok: true, status: 200, json: async () => ({ ...JOURNEYS[0], name: body.name }) }
      }
      if (init?.method === 'DELETE') {
        overrides.onDelete?.()
        return { ok: true, status: 204, json: async () => undefined }
      }
      if (url.endsWith('/steps')) {
        return { ok: true, status: 200, json: async () => STEPS }
      }
      if (url.includes('/journeys')) {
        return { ok: true, status: 200, json: async () => JOURNEYS }
      }
      return { ok: true, status: 200, json: async () => [] }
    }),
  )
}

function renderScreen() {
  return render(
    <DiscoverJourneys
      applicationId="app-1"
      discoveryStatus="complete"
      discoveryFailureReason={null}
      discoveryRunId="run-1"
    />,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DiscoverJourneys', () => {
  it('renders a candidate row with name and step count, no confidence/risk signal', async () => {
    stubFetch()
    renderScreen()

    await waitFor(() => {
      expect(screen.getByText('Checkout')).toBeTruthy()
    })
    expect(screen.getByText('2 steps')).toBeTruthy()
    expect(screen.queryByText(/confidence/i)).toBeNull()
    expect(screen.queryByText(/risk/i)).toBeNull()
  })

  it('hides the live discovery feed once Journeys have been discovered', async () => {
    stubFetch()
    renderScreen()

    await waitFor(() => {
      expect(screen.getByText('Checkout')).toBeTruthy()
    })
    expect(screen.queryByText('Live discovery feed')).toBeNull()
  })

  it('shows the live discovery feed while no Journeys have been discovered yet', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/captures')) {
          return {
            ok: true,
            status: 200,
            json: async () => [{ kind: 'page', summary: 'Home (/)', created_at: '2026-01-01T00:00:00Z' }],
          }
        }
        return { ok: true, status: 200, json: async () => [] }
      }),
    )
    renderScreen()

    await waitFor(() => {
      expect(screen.getByText('Live discovery feed')).toBeTruthy()
    })
  })

  it('selecting a row replaces the detail panel with that Journey’s step-by-step detail', async () => {
    stubFetch()
    renderScreen()
    await waitFor(() => screen.getByText('Checkout'))

    fireEvent.click(screen.getByText('Checkout'))

    await waitFor(() => {
      expect(screen.getByText('Login')).toBeTruthy()
    })
    expect(screen.getByText('MFA Verification')).toBeTruthy()
    expect(screen.getByText('Discovered flow · 2 steps')).toBeTruthy()
    const flow = within(screen.getByTestId('journey-flow'))
    expect(flow.getByText('1')).toBeTruthy()
    expect(flow.getByText('2')).toBeTruthy()
    // Business flow, not an API/route list — no route or method rendered.
    expect(screen.queryByText(/https:\/\//)).toBeNull()
    expect(screen.queryByText('GET')).toBeNull()
  })

  it('collapses consecutive steps sharing a stage into a single flow node', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/steps')) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              { step_order: 1, stage_label: 'Cart', route: '/cart', method: 'GET' },
              { step_order: 2, stage_label: 'Cart', route: '/cart/submit', method: 'POST' },
              { step_order: 3, stage_label: 'Checkout', route: '/checkout', method: 'GET' },
            ],
          }
        }
        return { ok: true, status: 200, json: async () => JOURNEYS }
      }),
    )
    renderScreen()
    await waitFor(() => screen.getByText('Checkout'))
    fireEvent.click(screen.getByText('Checkout'))

    await waitFor(() => {
      // row name + detail-panel header + flow node
      expect(screen.getAllByText('Checkout')).toHaveLength(3)
    })
    expect(screen.getAllByText('Cart')).toHaveLength(1)
    const flow = within(screen.getByTestId('journey-flow'))
    expect(flow.getByText('1')).toBeTruthy()
    expect(flow.getByText('2')).toBeTruthy()
  })

  it('renames a Journey via the ⋯ menu, updating the displayed name', async () => {
    let renamedTo: string | undefined
    stubFetch({
      onRename: (name) => {
        renamedTo = name
      },
    })
    renderScreen()
    await waitFor(() => screen.getByText('Checkout'))

    fireEvent.click(screen.getByRole('button', { name: 'Journey actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }))
    const input = screen.getByLabelText('Journey name')
    fireEvent.change(input, { target: { value: 'Guest Checkout' } })
    fireEvent.blur(input)

    await waitFor(() => {
      expect(screen.getByText('Guest Checkout')).toBeTruthy()
    })
    expect(renamedTo).toBe('Guest Checkout')
  })

  it('rejects renaming to an empty name and leaves the original in place', async () => {
    stubFetch()
    renderScreen()
    await waitFor(() => screen.getByText('Checkout'))

    fireEvent.click(screen.getByRole('button', { name: 'Journey actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }))
    const input = screen.getByLabelText('Journey name')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.blur(input)

    await waitFor(() => {
      expect(screen.getByText('Checkout')).toBeTruthy()
    })
  })

  it('deletes a Journey via the ⋯ menu, removing the row from the list entirely', async () => {
    let deleted = false
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    stubFetch({
      onDelete: () => {
        deleted = true
      },
    })
    renderScreen()
    await waitFor(() => screen.getByText('Checkout'))

    fireEvent.click(screen.getByRole('button', { name: 'Journey actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }))

    await waitFor(() => {
      expect(screen.queryByText('Checkout')).toBeNull()
    })
    expect(deleted).toBe(true)
  })

  it('does not delete when the confirmation is declined', async () => {
    let deleted = false
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    stubFetch({
      onDelete: () => {
        deleted = true
      },
    })
    renderScreen()
    await waitFor(() => screen.getByText('Checkout'))

    fireEvent.click(screen.getByRole('button', { name: 'Journey actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }))

    await waitFor(() => {
      expect(screen.getByText('Checkout')).toBeTruthy()
    })
    expect(deleted).toBe(false)
  })
})
