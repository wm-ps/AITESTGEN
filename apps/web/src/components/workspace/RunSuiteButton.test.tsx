import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_TARGET } from '../../runTarget'
import { RunSuiteHarness } from './RunSuiteHarness'

function setup() {
  const handlers = { onFullSuite: vi.fn(), onOpenJourneysDialog: vi.fn(), onOpenSuitesDialog: vi.fn() }
  render(<RunSuiteHarness {...handlers} />)
  fireEvent.click(screen.getByRole('button', { name: 'Run' }))
  return handlers
}

// The cards only choose; the footer button starts the choice.
function choose(card: string, action: string) {
  fireEvent.click(screen.getByText(card))
  fireEvent.click(screen.getByRole('button', { name: action }))
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
    choose('Test suites', 'Choose suite…')
    expect(handlers.onOpenSuitesDialog).toHaveBeenCalledWith(null, DEFAULT_TARGET)
    expect(handlers.onFullSuite).not.toHaveBeenCalled()
    expect(handlers.onOpenJourneysDialog).not.toHaveBeenCalled()
  })

  it('All test cases and Selective run still call their own handlers', () => {
    const full = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Run all test cases' }))
    expect(full.onFullSuite).toHaveBeenCalledWith(null, DEFAULT_TARGET)
    expect(full.onOpenSuitesDialog).not.toHaveBeenCalled()
  })

  it('Selective run still opens the journeys dialog', () => {
    const handlers = setup()
    choose('Selective run', 'Choose tests…')
    expect(handlers.onOpenJourneysDialog).toHaveBeenCalledWith(null, DEFAULT_TARGET)
    expect(handlers.onOpenSuitesDialog).not.toHaveBeenCalled()
  })
})

describe('RunSuiteButton browsers and window size', () => {
  it('starts on Chrome at 1280 × 720 and says nothing about extra browsers', () => {
    setup()
    expect(screen.getByRole('checkbox', { name: /Chrome/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Firefox/ })).not.toBeChecked()
    expect(screen.getByRole('combobox', { name: /Window size/ })).toHaveValue('1280x720')
    expect(screen.queryByText(/Each test runs on/)).not.toBeInTheDocument()
  })

  it('hands the chosen browsers and window size to the run', () => {
    const handlers = setup()
    fireEvent.click(screen.getByRole('checkbox', { name: /Firefox/ }))
    fireEvent.change(screen.getByRole('combobox', { name: /Window size/ }), { target: { value: '1920x1080' } })
    expect(screen.queryByText(/Each test runs on/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Run all test cases' }))

    expect(handlers.onFullSuite).toHaveBeenCalledWith(null, {
      browsers: ['chromium', 'firefox'],
      viewport: { width: 1920, height: 1080 },
    })
  })

  it('always keeps one browser selected', () => {
    setup()
    const chrome = screen.getByRole('checkbox', { name: /Chrome/ })
    fireEvent.click(chrome)
    expect(chrome).toBeChecked()
  })

  it('takes a custom size and refuses one that is out of range', () => {
    const handlers = setup()
    fireEvent.change(screen.getByRole('combobox', { name: /Window size/ }), { target: { value: 'custom' } })

    fireEvent.change(screen.getByLabelText('Width'), { target: { value: '700' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Width must be between 800 and 3840.')
    expect(screen.getByRole('button', { name: 'Run all test cases' })).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Width'), { target: { value: '1600' } })
    fireEvent.change(screen.getByLabelText('Height'), { target: { value: '900' } })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Run all test cases' }))

    expect(handlers.onFullSuite).toHaveBeenCalledWith(null, {
      browsers: ['chromium'],
      viewport: { width: 1600, height: 900 },
    })
  })

  it('does not remember the last choice: the dialog opens on the default again', () => {
    setup()
    fireEvent.click(screen.getByRole('checkbox', { name: /Safari/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    fireEvent.click(screen.getByRole('button', { name: 'Run' }))

    expect(screen.getByRole('checkbox', { name: /Safari/ })).not.toBeChecked()
  })

  it('does not close when the backdrop is clicked, only from Close, Cancel or Escape', () => {
    setup()
    fireEvent.click(screen.getByRole('dialog', { name: 'Run tests' }))
    expect(screen.getByRole('dialog', { name: 'Run tests' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Run' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('has no footer summary of the browsers and size', () => {
    setup()
    fireEvent.click(screen.getByRole('checkbox', { name: /Firefox/ }))
    expect(screen.queryByText(/2 browsers/)).not.toBeInTheDocument()
  })

  it('coming back keeps the earlier browsers, size and environment', () => {
    setup()
    fireEvent.click(screen.getByRole('checkbox', { name: /Firefox/ }))
    fireEvent.change(screen.getByRole('combobox', { name: /Window size/ }), { target: { value: '1920x1080' } })
    choose('Test suites', 'Choose suite…')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Back to Run tests' }))

    expect(screen.getByRole('checkbox', { name: /Firefox/ })).toBeChecked()
    expect(screen.getByRole('combobox', { name: /Window size/ })).toHaveValue('1920x1080')
  })
})
