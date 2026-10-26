import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ActivityItemRead } from '../api'
import { Activity } from './Activity'

const ADMIN = { name: 'Ada Lovelace', email: 'ada@example.com', role: 'admin' as const }

const FAILED_RUN: ActivityItemRead = {
  id: 'test_run:run-1',
  kind: 'test_run',
  created_at: new Date().toISOString(),
  category: 'test_runs',
  outcome: 'failed',
  summary: 'Test run #57 on Claims Portal — 41 passed, 1 failed',
  reason: '1 of 42 tests failed',
  actor: 'Schedule: Nightly Regression',
  application_id: 'app-1',
  application_name: 'Claims Portal',
  application_deleted: false,
  target_tab: 'runs',
  test_run_id: 'run-1',
  details: {},
}

const SETTING_CHANGE: ActivityItemRead = {
  ...FAILED_RUN,
  id: 'event:e-1',
  kind: 'event',
  category: 'settings',
  outcome: 'changed',
  summary: 'Changed max heal attempts from 3 to 5',
  reason: null,
  actor: 'Ada Lovelace',
  application_id: null,
  application_name: null,
  target_tab: null,
  test_run_id: null,
  details: { changes: [{ field: 'max heal attempts', before: '3', after: '5' }] },
}

const RUN = {
  id: 'run-1',
  passed_count: 41,
  failed_count: 1,
  timed_out_count: 0,
  errored_count: 0,
  blocked_count: 0,
  blocked_reason: null,
  started_at: null,
  completed_at: null,
  results: [
    {
      id: 'result-1',
      scenario_name: 'Submit claim form',
      journey_name: 'Claims',
      test_case_number: 12,
      status: 'failed',
      error_message: "Timeout 15000ms exceeded waiting for getByRole('button', { name: 'Submit' })",
      stack_trace: 'at claims.spec.ts:42',
    },
  ],
}

function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('/activity')
      ? {
          items: [FAILED_RUN, SETTING_CHANGE],
          next_cursor: null,
          facets: { category: { test_runs: 1, settings: 1 }, outcome: { failed: 1, changed: 1 }, application: { 'app-1': 1 }, total: { all: 2 } },
        }
      : url.includes('/test-runs/run-1')
        ? RUN
        : url.includes('/artifacts') || url.endsWith('/home')
          ? []
          : {}
    return { ok: true, status: 200, json: async () => body }
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Activity', () => {
  it('blocks anyone who is not an admin, without fetching activity', () => {
    const fetchMock = stubFetch()
    render(<Activity user={{ ...ADMIN, role: 'member' }} onOpen={() => {}} onBack={() => {}} />)

    expect(screen.getByText('No access')).toBeTruthy()
    expect(screen.getByText(/signed in as a member/)).toBeTruthy()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/activity'))).toBe(false)
  })

  it('filters from a dropdown that shows a count per option', async () => {
    const fetchMock = stubFetch()
    render(<Activity user={ADMIN} onOpen={() => {}} onBack={() => {}} />)

    await screen.findByText(FAILED_RUN.summary)
    fireEvent.click(screen.getByRole('button', { name: 'Result: All results' }))
    const failed = screen.getByRole('option', { name: /Failed/ })
    expect(failed.textContent).toContain('1')
    fireEvent.click(failed)

    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('outcome=failed'))).toBe(true))
    expect(await screen.findByText('Clear all')).toBeTruthy()
  })

  it('shows the exact error of a failed test in the detail panel', async () => {
    stubFetch()
    const onOpen = vi.fn()
    render(<Activity user={ADMIN} onOpen={onOpen} onBack={() => {}} />)

    fireEvent.click(await screen.findByText(FAILED_RUN.summary))

    await screen.findByText(/Timeout 15000ms exceeded/)
    expect(screen.getByText('TC-12 · Submit claim form')).toBeTruthy()
    fireEvent.click(screen.getByText('Open run'))
    expect(onOpen).toHaveBeenCalledWith(FAILED_RUN)
  })

  it('groups rows by day under Time / Event / By / Result, and Time flips the order on the server', async () => {
    const fetchMock = stubFetch()
    render(<Activity user={ADMIN} onOpen={() => {}} onBack={() => {}} />)

    await screen.findByText(FAILED_RUN.summary)
    for (const header of ['Time', 'Event', 'By', 'Result']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(`^${header}`) })).toBeTruthy()
    }
    expect(screen.getByText('Today')).toBeTruthy()
    expect(screen.getByText('Nightly Regression')).toBeTruthy() // schedule name, kind on its own line
    expect(screen.getAllByText('Schedule').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('columnheader', { name: /^Time/ }))
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('sort=oldest'))).toBe(true))
  })

  it('shows a settings change as before and after', async () => {
    stubFetch()
    render(<Activity user={ADMIN} onOpen={() => {}} onBack={() => {}} />)

    fireEvent.click(await screen.findByText(SETTING_CHANGE.summary))

    expect(await screen.findByText('What changed')).toBeTruthy()
    expect(screen.getByText('max heal attempts')).toBeTruthy()
  })
})
