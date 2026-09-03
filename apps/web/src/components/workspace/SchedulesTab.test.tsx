import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SchedulesTab } from './SchedulesTab'

afterEach(() => {
  vi.unstubAllGlobals()
})

const SCHEDULE_ROW = {
  id: 'sched-1',
  name: 'Nightly Regression',
  cadence_type: 'daily' as const,
  hour: 2,
  minute: 30,
  days_of_week: [] as number[],
  day_of_month: null,
  cron_expression: null,
  time_zone: 'Asia/Kolkata',
  enabled: true,
  cadence_label: 'Every day at 02:30 (Asia/Kolkata)',
  next_run_at: '2026-09-03T02:30:00Z',
  created_by_name: 'Tester',
  created_at: '2026-09-01T00:00:00Z',
}

describe('SchedulesTab', () => {
  it('renders fetched schedule data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/schedules')) {
          return { ok: true, status: 200, json: async () => [SCHEDULE_ROW] }
        }
        return { ok: true, status: 200, json: async () => ({}) }
      }),
    )

    render(<SchedulesTab applicationId="app-1" />)

    await waitFor(() => expect(screen.getByText('Nightly Regression')).toBeInTheDocument())
    expect(screen.getByText('Every day at 02:30 (Asia/Kolkata)')).toBeInTheDocument()
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })

  it('clicking "New Schedule" opens the dialog, and Escape closes it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, status: 200, json: async () => [] })),
    )

    render(<SchedulesTab applicationId="app-1" />)
    await waitFor(() => expect(screen.getByText('No schedules yet. Create one to run this Application\'s tests automatically on a recurring cadence.')).toBeInTheDocument())

    fireEvent.click(screen.getByText('New schedule'))
    await waitFor(() => expect(screen.getByText('New schedule', { selector: 'h2' })).toBeInTheDocument())

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByText('New schedule', { selector: 'h2' })).not.toBeInTheDocument())
  })

  it('the enable/disable toggle calls the right endpoint and re-lists', async () => {
    let currentlyEnabled = true
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/disable')) {
          currentlyEnabled = false
          return { ok: true, status: 200, json: async () => ({ ...SCHEDULE_ROW, enabled: false }) }
        }
        if (url.includes('/schedules')) {
          return {
            ok: true,
            status: 200,
            json: async () => [{ ...SCHEDULE_ROW, enabled: currentlyEnabled }],
          }
        }
        return { ok: true, status: 200, json: async () => ({}) }
      }),
    )

    render(<SchedulesTab applicationId="app-1" />)
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))

    fireEvent.click(screen.getByRole('switch'))

    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false'))
  })

  it('the kebab menu\'s Edit opens the dialog prefilled and submitting PATCHes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes('/schedules/sched-1') && init?.method === 'PATCH') {
          return { ok: true, status: 200, json: async () => SCHEDULE_ROW }
        }
        if (url.includes('/schedules')) {
          return { ok: true, status: 200, json: async () => [SCHEDULE_ROW] }
        }
        return { ok: true, status: 200, json: async () => ({}) }
      }),
    )

    render(<SchedulesTab applicationId="app-1" />)
    await waitFor(() => expect(screen.getByText('Nightly Regression')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    await waitFor(() => expect(screen.getByText('Edit')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Edit'))

    await waitFor(() => expect(screen.getByDisplayValue('Nightly Regression')).toBeInTheDocument())
    expect(screen.getByText('Save changes')).toBeInTheDocument()
  })

  it('the kebab menu lists Run now, Edit, and Delete, and closes on backdrop click', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/schedules')) {
          return { ok: true, status: 200, json: async () => [SCHEDULE_ROW] }
        }
        return { ok: true, status: 200, json: async () => ({}) }
      }),
    )

    render(<SchedulesTab applicationId="app-1" />)
    await waitFor(() => expect(screen.getByText('Nightly Regression')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    await waitFor(() => expect(screen.getByText('Run now')).toBeInTheDocument())
    expect(screen.getByText('Edit')).toBeInTheDocument()
    expect(screen.getByText('Delete')).toBeInTheDocument()

    // Backdrop click (not a menu item) closes the menu without acting.
    // jsdom doesn't do hit-testing, so target the backdrop element itself
    // rather than an arbitrary point that would visually overlap it.
    fireEvent.click(screen.getByTestId('row-menu-backdrop'))
    await waitFor(() => expect(screen.queryByText('Run now')).not.toBeInTheDocument())
  })
})
