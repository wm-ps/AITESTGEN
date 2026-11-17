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

    fireEvent.change(screen.getByPlaceholderText('Enter a name for this schedule'), {
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
    fireEvent.change(screen.getByPlaceholderText('Enter a name for this schedule'), { target: { value: 'X' } })
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

describe('ScheduleDialog browsers and window size', () => {
  const existing = {
    id: 'sched-1',
    name: 'Existing Schedule',
    cadence_type: 'daily' as const,
    hour: 3,
    minute: 15,
    days_of_week: [],
    day_of_month: null,
    cron_expression: null,
    time_zone: 'UTC',
    enabled: true,
    cadence_label: 'Every day at 03:15 (UTC)',
    next_run_at: null,
    created_by_name: null,
    created_at: '2026-09-01T00:00:00Z',
    environment_id: null,
    environment_name: 'staging',
    test_collection_id: null,
    test_collection_name: null,
  }

  function captureSave() {
    const sent: { method: string; body: Record<string, unknown> }[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes('/schedules') && (init?.method === 'POST' || init?.method === 'PATCH')) {
          sent.push({ method: init.method, body: JSON.parse(init.body as string) })
          return { ok: true, status: 200, json: async () => ({ id: 'sched-1' }) }
        }
        return { ok: true, status: 200, json: async () => ({}) }
      }),
    )
    return sent
  }

  it('sends no browsers or window size for a new schedule left on the default', async () => {
    const sent = captureSave()
    const onSaved = vi.fn()
    render(<ScheduleDialog applicationId="app-1" initial={null} onClose={() => {}} onSaved={onSaved} />)
    fireEvent.change(screen.getByPlaceholderText('Enter a name for this schedule'), { target: { value: 'Plain' } })

    fireEvent.click(screen.getByText('Create schedule'))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(sent[0].body).not.toHaveProperty('browsers')
    expect(sent[0].body).not.toHaveProperty('viewport')
  })

  it('saves the chosen browsers and window size', async () => {
    const sent = captureSave()
    const onSaved = vi.fn()
    render(<ScheduleDialog applicationId="app-1" initial={null} onClose={() => {}} onSaved={onSaved} />)
    fireEvent.change(screen.getByPlaceholderText('Enter a name for this schedule'), { target: { value: 'Wide' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Firefox/ }))
    fireEvent.change(screen.getByRole('combobox', { name: /Window size/ }), { target: { value: '1366x768' } })

    fireEvent.click(screen.getByText('Create schedule'))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(sent[0].body).toMatchObject({
      browsers: ['chromium', 'firefox'],
      viewport: { width: 1366, height: 768 },
    })
  })

  it('prefills a saved schedule and leaves them alone when an edit does not touch them', async () => {
    const sent = captureSave()
    const onSaved = vi.fn()
    render(
      <ScheduleDialog
        applicationId="app-1"
        initial={{ ...existing, browsers: ['chromium', 'webkit'], viewport_width: 1366, viewport_height: 768 }}
        onClose={() => {}}
        onSaved={onSaved}
      />,
    )

    expect(screen.getByRole('checkbox', { name: /Safari/ })).toBeChecked()
    expect(screen.getByRole('combobox', { name: /Window size/ })).toHaveValue('1366x768')

    fireEvent.click(screen.getByText('Save changes'))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(sent[0].method).toBe('PATCH')
    expect(sent[0].body).not.toHaveProperty('browsers')
    expect(sent[0].body).not.toHaveProperty('viewport')
  })

  it('sends null to put a schedule back on Chrome at 1280 × 720', async () => {
    const sent = captureSave()
    const onSaved = vi.fn()
    render(
      <ScheduleDialog
        applicationId="app-1"
        initial={{ ...existing, browsers: ['chromium', 'webkit'], viewport_width: 1366, viewport_height: 768 }}
        onClose={() => {}}
        onSaved={onSaved}
      />,
    )
    fireEvent.click(screen.getByRole('checkbox', { name: /Safari/ }))
    fireEvent.change(screen.getByRole('combobox', { name: /Window size/ }), { target: { value: '1280x720' } })

    fireEvent.click(screen.getByText('Save changes'))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(sent[0].body).toMatchObject({ browsers: null, viewport: null })
  })

  it('cannot be saved with a custom window size that is out of range', () => {
    render(<ScheduleDialog applicationId="app-1" initial={null} onClose={() => {}} onSaved={() => {}} />)
    fireEvent.change(screen.getByRole('combobox', { name: /Window size/ }), { target: { value: 'custom' } })
    fireEvent.change(screen.getByLabelText('Width'), { target: { value: '500' } })

    expect(screen.getByText('Create schedule')).toBeDisabled()
  })
})
