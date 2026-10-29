import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ExplorerTab } from './ExplorerTab'
import type { ExplorerQuestion, ExplorerRun } from './explorerApi'

const run: ExplorerRun = {
  id: 'r1',
  application_id: 'a1',
  status: 'tested',
  headline: 'Done',
  health_score: 90,
  requirements_first: false,
  brief: null,
  brief_confirmed_at: null,
  notes: null,
  error: null,
  created_at: '2026-10-19T08:00:00Z',
  updated_at: '2026-10-19T09:00:00Z',
  counts: { screens: 0, hidden_hints: 0, health_issues: 0, hidden_screens: 0, possible_bugs: 0, missions_total: 0, missions_done: 0, missions_running: 0, tests_total: 0, tests_proven: 0, tests_known_bugs: 0, tests_building: 0, questions_open: 1 },
}
const question: ExplorerQuestion = {
  id: 'q1',
  kind: 'data',
  question: 'What policy number should I use?',
  why: null,
  options: [],
  shot_id: null,
  status: 'open',
  answer: null,
  answered_at: null,
  created_at: '2026-10-19T08:30:00Z',
  mission_title: null,
}

vi.mock('./explorerApi', async (orig) => {
  const real = await orig<typeof import('./explorerApi')>()
  return {
    ...real,
    explorerApi: {
      ...real.explorerApi,
      latestRun: vi.fn(async () => run),
      events: vi.fn(async () => []),
      getRun: vi.fn(async () => run),
      health: vi.fn(async () => []),
      questions: vi.fn(async () => [question]),
      map: vi.fn(async () => ({ screens: [], edges: [] })),
      missions: vi.fn(async () => []),
      tests: vi.fn(async () => []),
      knowledge: vi.fn(async () => []),
    },
  }
})

describe('ExplorerTab expired run', () => {
  it('explains the expiry, offers only a new run, and never Resume or Confirm', async () => {
    const { explorerApi } = await import('./explorerApi')
    const expired = { ...run, status: 'expired' as const, headline: 'Expired: not confirmed within 14 days', brief: { app_name: 'FNOL' } }
    vi.mocked(explorerApi.latestRun).mockResolvedValueOnce(expired)
    render(<ExplorerTab applicationId="a1" applicationName="FNOL" applicationUrl="https://x" />)

    expect(await screen.findByText('This App Summary expired.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Resume/ })).toBeNull()
    fireEvent.click(screen.getByRole('tab', { name: /What it learned/ }))
    expect(screen.getByText('Expired: not confirmed in time')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Confirm/ })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Start a new run/ }))
    expect(screen.getByRole('button', { name: /Start exploring/ })).toBeTruthy()
  })
})

describe('ExplorerTab', () => {
  it('asks questions from a header button with a count, not from a tab', async () => {
    render(<ExplorerTab applicationId="a1" applicationName="FNOL" applicationUrl="https://x" />)
    const button = await screen.findByRole('button', { name: 'Questions, 1 open' })
    expect(screen.queryByRole('tab', { name: /Questions/ })).toBeNull()

    fireEvent.click(button)
    const dialog = screen.getByRole('dialog', { name: 'Questions for you' })
    expect(within(dialog).getByText('What policy number should I use?')).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('orders the tabs Live, What it learned, Screens, Scenarios', async () => {
    render(<ExplorerTab applicationId="a1" applicationName="FNOL" applicationUrl="https://x" />)
    await screen.findByRole('tablist')
    const names = screen.getAllByRole('tab').map((t) => t.textContent?.replace(/\d+$/, '').trim())
    expect(names).toEqual(['Live', 'What it learned', 'Screens', 'Scenarios'])
  })

  it('moves between tabs with the arrow keys', async () => {
    render(<ExplorerTab applicationId="a1" applicationName="FNOL" applicationUrl="https://x" />)
    const live = await screen.findByRole('tab', { name: /Live/ })
    fireEvent.keyDown(live, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: /What it learned/ }).getAttribute('aria-selected')).toBe('true')
    fireEvent.keyDown(screen.getByRole('tab', { name: /What it learned/ }), { key: 'ArrowLeft' })
    expect(screen.getByRole('tab', { name: /Live/ }).getAttribute('aria-selected')).toBe('true')
  })
})

describe('ExplorerTab authoring run', () => {
  it('hands over to Test cases once a watched authoring run finishes, not before', async () => {
    const { explorerApi } = await import('./explorerApi')
    const authoring = { ...run, prompt: 'Search policy POL-1', brief: { app_name: 'FNOL' } }
    vi.mocked(explorerApi.latestRun).mockResolvedValueOnce({ ...authoring, status: 'testing' as const })
    vi.mocked(explorerApi.getRun).mockResolvedValue({ ...authoring, status: 'tested' as const, counts: { ...run.counts, tests_proven: 1 } })
    const onAuthoringDone = vi.fn()
    render(<ExplorerTab applicationId="a1" applicationName="FNOL" applicationUrl="https://x" onAuthoringDone={onAuthoringDone} />)
    await screen.findByRole('button', { name: 'Questions, 1 open' })
    expect(onAuthoringDone).not.toHaveBeenCalled()
    await waitFor(() => expect(onAuthoringDone).toHaveBeenCalledTimes(1), { timeout: 5000 })
    vi.mocked(explorerApi.getRun).mockResolvedValue(run)
  })

  it('stays on Explorer when the authoring run added no test cases', async () => {
    const { explorerApi } = await import('./explorerApi')
    const authoring = { ...run, prompt: 'Check Brad Smith', brief: { app_name: 'SalesVision' } }
    vi.mocked(explorerApi.latestRun).mockResolvedValueOnce({ ...authoring, status: 'testing' as const })
    vi.mocked(explorerApi.getRun).mockResolvedValue({ ...authoring, status: 'tested' as const })
    const onAuthoringDone = vi.fn()
    render(<ExplorerTab applicationId="a1" applicationName="SalesVision" applicationUrl="https://x" onAuthoringDone={onAuthoringDone} />)
    await waitFor(() => expect(explorerApi.getRun).toHaveBeenCalled(), { timeout: 5000 })
    await new Promise((r) => setTimeout(r, 300))
    expect(onAuthoringDone).not.toHaveBeenCalled()
    vi.mocked(explorerApi.getRun).mockResolvedValue(run)
  })

  it('stays put when an authoring run that already finished is opened', async () => {
    const { explorerApi } = await import('./explorerApi')
    vi.mocked(explorerApi.latestRun).mockResolvedValueOnce({ ...run, prompt: 'Search policy POL-1' })
    const onAuthoringDone = vi.fn()
    render(<ExplorerTab applicationId="a1" applicationName="FNOL" applicationUrl="https://x" onAuthoringDone={onAuthoringDone} />)
    await screen.findByRole('button', { name: 'Questions, 1 open' })
    expect(onAuthoringDone).not.toHaveBeenCalled()
  })
})
