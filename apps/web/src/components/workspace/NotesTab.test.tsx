import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NotesTab } from './NotesTab'

// `@testing-library/jest-dom` isn't a dependency of this project — every
// query below relies only on core Testing Library behavior (a `getBy*`
// query throws on its own when nothing matches) rather than a
// `.toBeInTheDocument()`/`.toHaveValue()` jest-dom matcher.

afterEach(() => {
  vi.unstubAllGlobals()
})

const EMPTY_APPLICATION = {
  id: 'app-1',
  name: 'Wealth Management Portal',
  url: 'https://app.example.com',
  login_url: null,
  environment: 'staging',
  auth_method: 'standard_login',
  created_at: '2026-09-01T00:00:00Z',
  discovery_run_id: 'run-1',
  discovery_status: 'complete',
  discovery_stage: null,
  discovery_failure_reason: null,
  discovery_coverage_summary: null,
  application_context: null,
}

describe('NotesTab', () => {
  it('shows the empty state when no notes are saved yet', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => EMPTY_APPLICATION })))

    render(<NotesTab applicationId="app-1" />)

    await waitFor(() => screen.getByText('Application context'))
    const businessGoal = screen.getByPlaceholderText(
      'Describe the primary purpose of the application and the outcomes it should deliver',
    ) as HTMLTextAreaElement
    expect(businessGoal.value).toBe('')
    // Live character counter starts at 0 for every one of the 4 fields.
    expect(screen.getAllByText('0 / 2,000').length).toBe(4)
  })

  it('displays previously saved notes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          ...EMPTY_APPLICATION,
          application_context: {
            business_goal: 'Manage clients, accounts and investments.',
            business_domain: null,
            business_rules: ['Engagements shown depend on the selected tenant.'],
            additional_context: null,
          },
        }),
      })),
    )

    render(<NotesTab applicationId="app-1" />)

    await waitFor(() => screen.getByDisplayValue('Manage clients, accounts and investments.'))
    screen.getByDisplayValue('Engagements shown depend on the selected tenant.')
  })

  it('editing and saving sends the updated notes and reloads them', async () => {
    let saved: unknown = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('/context')) {
          saved = JSON.parse(init?.body as string)
          return { ok: true, status: 200, json: async () => ({ ...EMPTY_APPLICATION, application_context: saved }) }
        }
        return { ok: true, status: 200, json: async () => EMPTY_APPLICATION }
      }),
    )

    render(<NotesTab applicationId="app-1" />)
    await waitFor(() => screen.getByText('Application context'))

    const businessGoalInput = screen.getByPlaceholderText(
      'Describe the primary purpose of the application and the outcomes it should deliver',
    )
    fireEvent.change(businessGoalInput, {
      target: { value: 'Manage clients, accounts and investments.' },
    })
    // Character counter tracks the live value.
    screen.getByText('41 / 2,000')

    fireEvent.click(screen.getByRole('button', { name: 'Save notes' }))

    await waitFor(() => screen.getByText('Notes saved.'))
    expect(saved).toMatchObject({ business_goal: 'Manage clients, accounts and investments.' })
  })

  it('blank fields are saved as null, not an empty array', async () => {
    let saved: unknown = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('/context')) {
          saved = JSON.parse(init?.body as string)
          return { ok: true, status: 200, json: async () => ({ ...EMPTY_APPLICATION, application_context: saved }) }
        }
        return { ok: true, status: 200, json: async () => EMPTY_APPLICATION }
      }),
    )

    render(<NotesTab applicationId="app-1" />)
    await waitFor(() => screen.getByText('Application context'))

    fireEvent.click(screen.getByRole('button', { name: 'Save notes' }))

    await waitFor(() => screen.getByText('Notes saved.'))
    expect(saved).toMatchObject({ business_goal: null, business_rules: null })
  })

  it('shows a load error when fetching the application fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, json: async () => ({ detail: 'boom' }) })))

    render(<NotesTab applicationId="app-1" />)

    await waitFor(() => screen.getByRole('alert'))
    expect(screen.getByRole('alert').textContent).toBe('boom')
  })
})
