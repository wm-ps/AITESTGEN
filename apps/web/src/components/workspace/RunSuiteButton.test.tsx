import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RunSuiteButton } from './RunSuiteButton'

function setup() {
  const handlers = { onFullSuite: vi.fn(), onOpenJourneysDialog: vi.fn(), onOpenSuitesDialog: vi.fn() }
  render(<RunSuiteButton running={false} {...handlers} />)
  fireEvent.click(screen.getByRole('button', { name: /Run/ }))
  return handlers
}

describe('RunSuiteButton', () => {
  it('offers all three ways to run', () => {
    setup()
    expect(screen.getByText('All test cases')).toBeInTheDocument()
    expect(screen.getByText('Selective run')).toBeInTheDocument()
    expect(screen.getByText('Test suites')).toBeInTheDocument()
  })

  it('Test suites opens the suites dialog and the other two are unchanged', () => {
    const handlers = setup()
    fireEvent.click(screen.getByText('Test suites'))
    expect(handlers.onOpenSuitesDialog).toHaveBeenCalledWith(null)
    expect(handlers.onFullSuite).not.toHaveBeenCalled()
    expect(handlers.onOpenJourneysDialog).not.toHaveBeenCalled()
  })

  it('All test cases and Selective run still call their own handlers', () => {
    const full = setup()
    fireEvent.click(screen.getByText('All test cases'))
    expect(full.onFullSuite).toHaveBeenCalledWith(null)
    expect(full.onOpenSuitesDialog).not.toHaveBeenCalled()
  })

  it('Selective run still opens the journeys dialog', () => {
    const handlers = setup()
    fireEvent.click(screen.getByText('Selective run'))
    expect(handlers.onOpenJourneysDialog).toHaveBeenCalledWith(null)
    expect(handlers.onOpenSuitesDialog).not.toHaveBeenCalled()
  })
})
