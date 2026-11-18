import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { TestSuiteTab } from './TestSuiteTab'
import { api } from '../../api'
import { explorerApi, type ExplorerRun } from '../../explorer/explorerApi'

// An authoring run's possible bugs are not test cases until answered: Test
// cases says they wait, and "Answer now" goes to them — wherever the user is
// when the run ends (asleep laptop, another tab, a reload).
function run(over: Partial<ExplorerRun>): ExplorerRun {
  return {
    id: 'r1',
    status: 'tested',
    prompt: 'write test cases for the add opportunity flow',
    counts: { tests_proven: 19, tests_known_bugs: 9 },
    ...over,
  } as unknown as ExplorerRun
}

beforeEach(() => {
  vi.restoreAllMocks()
  const empty = { items: [], total: 0 } as never
  vi.spyOn(api, 'getTestSuiteStatus').mockResolvedValue(empty)
  vi.spyOn(api, 'listScenarios').mockResolvedValue([] as never)
  vi.spyOn(api, 'listTestSuites').mockResolvedValue([] as never)
})

describe('Test cases: possible bugs waiting for an answer', () => {
  it('says how many wait and opens them', async () => {
    vi.spyOn(explorerApi, 'latestRun').mockResolvedValue(run({}))
    const answer = vi.fn()
    render(<TestSuiteTab applicationId="app" onAnswerPossibleBugs={answer} />)
    expect(await screen.findByText('9 possible bugs from your request wait for your answer')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Answer now' }))
    expect(answer).toHaveBeenCalledOnce()
  })

  it('says nothing once they are answered, or for an exploration', async () => {
    const latest = vi.spyOn(explorerApi, 'latestRun')
    latest.mockResolvedValue(run({ counts: { tests_proven: 19, tests_known_bugs: 0 } } as never))
    const { unmount } = render(<TestSuiteTab applicationId="app" onAnswerPossibleBugs={() => {}} />)
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByText(/wait for your answer/)).toBeNull()
    unmount()
    latest.mockResolvedValue(run({ prompt: null }))
    render(<TestSuiteTab applicationId="app" onAnswerPossibleBugs={() => {}} />)
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByText(/wait for your answer/)).toBeNull()
  })
})
