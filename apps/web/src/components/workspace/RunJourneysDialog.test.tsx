import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type TestSuiteRead } from '../../api'
import { RunJourneysDialog } from './RunJourneysDialog'

function suite(id: string, journey: string, caseCount: number): TestSuiteRead {
  return {
    id,
    name: journey,
    journey_name: journey,
    status: 'complete',
    test_cases: Array.from({ length: caseCount }, (_, i) => ({
      id: `${id}-tc${i + 1}`,
      name: `${journey} case ${i + 1}`,
      test_case_number: i + 1,
    })),
  } as unknown as TestSuiteRead
}

const SUITES = [suite('s1', 'Authentication', 4), suite('s2', 'Claim submission', 3), suite('s3', 'Empty journey', 0)]

async function renderDialog(onExecute = vi.fn(), onClose = vi.fn()) {
  vi.spyOn(api, 'listTestSuites').mockResolvedValue(SUITES)
  render(<RunJourneysDialog applicationId="app-1" onClose={onClose} onExecute={onExecute} />)
  await screen.findByText('Authentication')
  return { onExecute, onClose }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RunJourneysDialog', () => {
  it('starts with nothing selected and hides journeys that have no test cases', async () => {
    await renderDialog()
    expect(screen.getByText('0 of 2 selected')).toBeInTheDocument()
    expect(screen.getByText('0 test cases across 0 journeys')).toBeInTheDocument()
    expect(screen.queryByText('Empty journey')).not.toBeInTheDocument()
  })

  it('Select all / Clear cover every journey and update the footer and button', async () => {
    await renderDialog()
    fireEvent.click(screen.getByText('Select all'))
    expect(screen.getByText('2 of 2 selected')).toBeInTheDocument()
    expect(screen.getByText('7 test cases across 2 journeys')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Run 2 journeys/ })).toBeInTheDocument()

    fireEvent.click(screen.getByText('Clear'))
    expect(screen.getByText('0 test cases across 0 journeys')).toBeInTheDocument()
  })

  it('search filters by journey name only, keeps selections, and counts hidden selected journeys', async () => {
    await renderDialog()
    fireEvent.click(screen.getByText('Select all'))
    fireEvent.change(screen.getByLabelText('Search journeys'), { target: { value: 'clai' } })

    expect(screen.queryByText('Authentication')).not.toBeInTheDocument()
    expect(screen.getByText('Claim submission')).toBeInTheDocument()
    expect(screen.getByText(/1 selected journey is hidden by your search/)).toBeInTheDocument()

    // Test-case names are not searched.
    fireEvent.change(screen.getByLabelText('Search journeys'), { target: { value: 'case 1' } })
    expect(screen.getByText('No journeys match "case 1"')).toBeInTheDocument()
    expect(screen.getByText(/2 selected journeys are hidden/)).toBeInTheDocument()
    expect(screen.getByText('2 of 2 selected')).toBeInTheDocument()
  })

  it('shows the inline error on blur and on Run click, and does not execute', async () => {
    const { onExecute } = await renderDialog()
    fireEvent.click(screen.getByText('Select all'))

    const nameInput = screen.getByPlaceholderText('Enter a name for this run')
    fireEvent.blur(nameInput)
    expect(screen.getByText('Enter a run name to continue')).toBeInTheDocument()

    fireEvent.change(nameInput, { target: { value: 'x' } })
    expect(screen.queryByText('Enter a run name to continue')).not.toBeInTheDocument()

    fireEvent.change(nameInput, { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: /Run 2 journeys/ }))
    expect(screen.getByText('Enter a run name to continue')).toBeInTheDocument()
    expect(onExecute).not.toHaveBeenCalled()
  })

  it('executes with the trimmed name and every selected test case id, honouring unticked cases', async () => {
    const { onExecute } = await renderDialog()
    fireEvent.click(screen.getByText('Select all'))
    fireEvent.click(screen.getAllByLabelText('Expand')[0])
    fireEvent.click(screen.getAllByRole('checkbox')[1]) // first Authentication case
    fireEvent.change(screen.getByPlaceholderText('Enter a name for this run'), { target: { value: ' Smoke ' } })
    fireEvent.click(screen.getByRole('button', { name: /Run 2 journeys/ }))

    await waitFor(() => expect(onExecute).toHaveBeenCalledTimes(1))
    const [name, ids] = onExecute.mock.calls[0]
    expect(name).toBe('Smoke')
    expect(ids).toHaveLength(6)
    expect(ids).not.toContain('s1-tc1')
  })

  it('does not execute with a name but no selection', async () => {
    const { onExecute } = await renderDialog()
    fireEvent.change(screen.getByPlaceholderText('Enter a name for this run'), { target: { value: 'Smoke' } })
    fireEvent.click(screen.getByRole('button', { name: /Run journeys/ }))
    expect(onExecute).not.toHaveBeenCalled()
  })

  it('first Esc clears the search, second Esc closes', async () => {
    const { onClose } = await renderDialog()
    const search = screen.getByLabelText('Search journeys')
    fireEvent.change(search, { target: { value: 'au' } })
    fireEvent.keyDown(search, { key: 'Escape' })
    expect(search).toHaveValue('')
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.keyDown(search, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
