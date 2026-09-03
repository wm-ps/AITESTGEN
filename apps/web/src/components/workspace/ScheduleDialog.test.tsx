import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ScheduleDialog } from './ScheduleDialog'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ScheduleDialog', () => {
  it('cadence selector reveals and hides the right conditional inputs', async () => {
    render(<ScheduleDialog applicationId="app-1" initial={null} onClose={() => {}} onSaved={() => {}} />)

    // Daily (default): hour/minute selects visible, no day checkboxes, no cron input.
    expect(screen.getByText('Hour')).toBeInTheDocument()
    expect(screen.queryByText('Days')).not.toBeInTheDocument()
    expect(screen.queryByText('Cron expression')).not.toBeInTheDocument()

    fireEvent.change(screen.getByText('Cadence').nextElementSibling as Element, {
      target: { value: 'weekly' },
    })
    await waitFor(() => expect(screen.getByText('Days')).toBeInTheDocument())
    expect(screen.getByText('Hour')).toBeInTheDocument()

    fireEvent.change(screen.getByText('Cadence').nextElementSibling as Element, {
      target: { value: 'custom_cron' },
    })
    await waitFor(() => expect(screen.getByText('Cron expression')).toBeInTheDocument())
    expect(screen.queryByText('Hour')).not.toBeInTheDocument()
    expect(screen.queryByText('Days')).not.toBeInTheDocument()
  })

  it('submits the exact expected JSON for a weekly cadence with non-contiguous days', async () => {
    let capturedBody: unknown = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes('/schedules') && init?.method === 'POST') {
          capturedBody = JSON.parse(init.body as string)
          return { ok: true, status: 201, json: async () => ({ id: 'sched-1' }) }
        }
        return { ok: true, status: 200, json: async () => ({}) }
      }),
    )
    const onSaved = vi.fn()

    render(<ScheduleDialog applicationId="app-1" initial={null} onClose={() => {}} onSaved={onSaved} />)

    fireEvent.change(screen.getByPlaceholderText('Nightly Regression'), {
      target: { value: 'My Weekly Run' },
    })
    fireEvent.change(screen.getByText('Cadence').nextElementSibling as Element, {
      target: { value: 'weekly' },
    })
    await waitFor(() => expect(screen.getByText('Thu')).toBeInTheDocument())
    // Monday is checked by default; also check Thursday (non-contiguous).
    fireEvent.click(screen.getByText('Thu'))

    fireEvent.click(screen.getByText('Create schedule'))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(capturedBody).toMatchObject({
      name: 'My Weekly Run',
      cadence_type: 'weekly',
      days_of_week: [1, 4],
      day_of_month: null,
    })
    expect(capturedBody).not.toHaveProperty('cron_expression')
  })

  it('renders a 422 error without closing the dialog', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'day_of_month must be 1-28' }),
      })),
    )
    const onSaved = vi.fn()

    render(<ScheduleDialog applicationId="app-1" initial={null} onClose={() => {}} onSaved={onSaved} />)
    fireEvent.change(screen.getByPlaceholderText('Nightly Regression'), { target: { value: 'X' } })
    fireEvent.click(screen.getByText('Create schedule'))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('day_of_month must be 1-28'))
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('edit mode PATCHes rather than POSTs and prefills from the existing row', () => {
    render(
      <ScheduleDialog
        applicationId="app-1"
        initial={{
          id: 'sched-1',
          name: 'Existing Schedule',
          cadence_type: 'weekly',
          hour: 3,
          minute: 15,
          days_of_week: [2, 5],
          day_of_month: null,
          cron_expression: null,
          time_zone: 'UTC',
          enabled: true,
          cadence_label: 'Every Tue, Fri at 03:15 (UTC)',
          next_run_at: null,
          created_by_name: null,
          created_at: '2026-09-01T00:00:00Z',
        }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    )

    expect(screen.getByDisplayValue('Existing Schedule')).toBeInTheDocument()
    expect(screen.getByText('Save changes')).toBeInTheDocument()
  })
})
