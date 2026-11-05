import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../../api'
import { SelectTestCasesDialog } from './SelectTestCasesDialog'
import { detail, summary, testCase } from './fixtures'

const CASES = [
  testCase('a', 'Sign in with valid credentials', 'Authentication', 1, [
    { id: 'c1', name: 'Smoke' },
    { id: 'c2', name: 'Regression' },
  ]),
  testCase('b', 'Sign in with an invalid password', 'Authentication', 2),
  testCase('c', 'Submit a claim', 'Claims', 3),
]

async function renderDialog({ members = ['a'], unavailable = 0 } = {}) {
  vi.spyOn(api, 'listCollectionCases').mockResolvedValue(CASES)
  vi.spyOn(api, 'getCollection').mockResolvedValue(
    detail({
      available: members.map((id) => ({ scenario_id: id, name: id, journey_name: 'x' })),
      unavailable: Array.from({ length: unavailable }, (_, i) => ({ scenario_id: `gone-${i}`, name: 'gone' })),
    }),
  )
  const save = vi.spyOn(api, 'changeCollectionMembers').mockResolvedValue(summary())
  const onSaved = vi.fn()
  const onClose = vi.fn()
  render(
    <SelectTestCasesDialog
      applicationId="app-1"
      suite={{ id: 'c1', name: 'Smoke' }}
      onClose={onClose}
      onSaved={onSaved}
    />,
  )
  await screen.findByText('Sign in with valid credentials')
  return { save, onSaved, onClose }
}

afterEach(() => vi.restoreAllMocks())

describe('SelectTestCasesDialog', () => {
  it('shows the suite, counts, and which other suites a case is in', async () => {
    await renderDialog({ unavailable: 1 })
    expect(screen.getByText('Suite: Smoke')).toBeInTheDocument()
    // the case is in Smoke (this suite) and Regression: only the other one is named
    expect(screen.getByText(/TC-001 · also in Regression/)).toBeInTheDocument()
    expect(screen.getByText('1 of 3 test cases selected · 1 unavailable kept')).toBeInTheDocument()
    expect(screen.getByText('1/3')).toBeInTheDocument() // All journeys row
  })

  it('a journey checkbox toggles all its cases and Save sends only the diff', async () => {
    const { save, onSaved } = await renderDialog()
    fireEvent.click(screen.getByLabelText('Select Claims'))
    fireEvent.click(screen.getByLabelText('Select Authentication')) // 1 of 2 on -> turns all on
    expect(screen.getByText('3 of 3 test cases selected')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save test cases' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(save).toHaveBeenCalledWith('c1', { add: expect.arrayContaining(['b', 'c']), remove: [] })
    expect(save.mock.calls[0][1].add).toHaveLength(2)
  })

  it('Clear all removes only available members, never unavailable ones', async () => {
    const { save } = await renderDialog({ members: ['a', 'b'], unavailable: 1 })
    fireEvent.click(screen.getByText('Clear all'))
    fireEvent.click(screen.getByRole('button', { name: 'Save test cases' }))
    await waitFor(() => expect(save).toHaveBeenCalled())
    expect(save).toHaveBeenCalledWith('c1', { add: [], remove: expect.arrayContaining(['a', 'b']) })
    expect(save.mock.calls[0][1].remove).toHaveLength(2)
  })

  it('clicking a journey shows only its cases; search narrows within the scope', async () => {
    await renderDialog()
    fireEvent.click(screen.getByText('Claims'))
    expect(screen.getByText('Submit a claim')).toBeInTheDocument()
    expect(screen.queryByText('Sign in with an invalid password')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('All journeys'))
    fireEvent.change(screen.getByLabelText('Search test cases'), { target: { value: 'invalid' } })
    expect(screen.getByText('Sign in with an invalid password')).toBeInTheDocument()
    expect(screen.queryByText('Submit a claim')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Search journeys'), { target: { value: 'zzz' } })
    expect(screen.getByText(/No journeys match/)).toBeInTheDocument()
  })

  it('saving with no changes just closes', async () => {
    const { save, onClose } = await renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Save test cases' }))
    expect(onClose).toHaveBeenCalled()
    expect(save).not.toHaveBeenCalled()
  })

  it('shows an error and stays open when saving fails', async () => {
    const { save, onSaved } = await renderDialog()
    save.mockRejectedValueOnce(new Error('boom'))
    fireEvent.click(screen.getByLabelText('Select Claims'))
    fireEvent.click(screen.getByRole('button', { name: 'Save test cases' }))
    await screen.findByText('Could not save the test cases. Try again.')
    expect(onSaved).not.toHaveBeenCalled()
  })
})
