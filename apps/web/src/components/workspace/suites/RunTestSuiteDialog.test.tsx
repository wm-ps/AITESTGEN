import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../../api'
import { RunTestSuiteDialog } from './RunTestSuiteDialog'
import { summary } from './fixtures'

const SUITES = [
  summary({ id: 'smoke', name: 'Smoke', test_case_count: 4, unavailable_count: 1 }),
  summary({ id: 'regression', name: 'Regression', test_case_count: 7 }),
  summary({ id: 'empty', name: 'Payments', test_case_count: 0, unavailable_count: 2 }),
]

async function renderDialog(onRun = vi.fn(), onClose = vi.fn()) {
  vi.spyOn(api, 'listCollections').mockResolvedValue(SUITES)
  render(
    <RunTestSuiteDialog applicationId="app-1" initialEnvironmentId="env-1" onClose={onClose} onRun={onRun} />,
  )
  await screen.findByText('Smoke')
  return { onRun, onClose }
}

afterEach(() => vi.restoreAllMocks())

describe('RunTestSuiteDialog', () => {
  it('lists every suite with what will run and an unavailable badge', async () => {
    await renderDialog()
    expect(screen.getByText('4 test cases will run')).toBeInTheDocument()
    expect(screen.getByText('7 test cases will run')).toBeInTheDocument()
    expect(screen.getByText('1 unavailable')).toBeInTheDocument()
    expect(screen.getByText('Unavailable test cases are skipped.')).toBeInTheDocument()
  })

  it('preselects the first runnable suite and runs it with the environment', async () => {
    const { onRun } = await renderDialog()
    fireEvent.click(screen.getByRole('button', { name: /Run 4 test cases/ }))
    expect(onRun).toHaveBeenCalledWith('smoke', 'env-1')
  })

  it('switching suite changes the run button', async () => {
    const { onRun } = await renderDialog()
    fireEvent.click(screen.getByRole('radio', { name: /Regression/ }))
    fireEvent.click(screen.getByRole('button', { name: /Run 7 test cases/ }))
    expect(onRun).toHaveBeenCalledWith('regression', 'env-1')
  })

  it('a suite with nothing runnable cannot be chosen or run', async () => {
    const { onRun } = await renderDialog()
    const empty = screen.getByRole('radio', { name: /Payments/ })
    expect(empty).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('No test cases to run')).toBeInTheDocument()
    fireEvent.click(empty)
    // still on the preselected suite
    fireEvent.click(screen.getByRole('button', { name: /Run 4 test cases/ }))
    expect(onRun).toHaveBeenCalledWith('smoke', 'env-1')
  })

  it('shows a helpful line when there are no suites, and cannot run', async () => {
    vi.spyOn(api, 'listCollections').mockResolvedValue([])
    const onRun = vi.fn()
    render(<RunTestSuiteDialog applicationId="app-1" initialEnvironmentId={null} onClose={vi.fn()} onRun={onRun} />)
    await screen.findByText(/No test suites yet/)
    fireEvent.click(screen.getByRole('button', { name: /Run test cases/ }))
    expect(onRun).not.toHaveBeenCalled()
  })
})
