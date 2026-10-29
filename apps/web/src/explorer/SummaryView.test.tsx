import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SummaryView } from './SummaryView'
import type { ExplorerRun, ExplorerScreen } from './explorerApi'

const runWith = (answer: string) =>
  ({
    id: 'r1',
    status: 'awaiting_confirmation',
    brief_confirmed_at: null,
    brief: { app_name: 'FNOL', questions_for_you: [{ question: 'Which policy?', options: ['POL-1'], answer }] },
  }) as unknown as ExplorerRun

const confirmButton = () => screen.getByRole('button', { name: /Looks right — confirm/ })

describe('SummaryView', () => {
  it('calls the coverage section Goal', () => {
    render(<SummaryView run={runWith('POL-1')} screens={[]} onSave={vi.fn(async () => {})} onConfirm={vi.fn(async () => {})} />)
    expect(screen.getByText('Goal')).toBeTruthy()
    expect(screen.queryByText('What to cover')).toBeNull()
  })

  it('does not confirm while a question is unanswered, and says why', () => {
    const onConfirm = vi.fn(async () => {})
    render(<SummaryView run={runWith('')} screens={[]} onSave={vi.fn(async () => {})} onConfirm={onConfirm} />)
    fireEvent.click(confirmButton())
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.getByText('Answer the questions first — they change what Explorer tests.')).toBeTruthy()
  })

  it('confirms once every question is answered', () => {
    const onConfirm = vi.fn(async () => {})
    render(<SummaryView run={runWith('POL-1')} screens={[]} onSave={vi.fn(async () => {})} onConfirm={onConfirm} />)
    fireEvent.click(confirmButton())
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('leaves out pages picked by typing, shown as chips, and shows no screenshots', async () => {
    const onSave = vi.fn(async () => {})
    const screens = [
      { name: 'Change password', shot_id: 's1' },
      { name: 'Transfer funds', shot_id: 's2' },
    ] as unknown as ExplorerScreen[]
    const { container } = render(<SummaryView run={runWith('POL-1')} screens={screens} onSave={onSave} onConfirm={vi.fn(async () => {})} />)
    expect(container.querySelector('img')).toBeNull()

    const field = screen.getByLabelText(/Pages to leave out/)
    fireEvent.change(field, { target: { value: 'chan' } })
    expect(screen.queryByRole('option', { name: 'Transfer funds' })).toBeNull()
    fireEvent.click(screen.getByRole('option', { name: 'Change password' }))
    await waitFor(() => expect(onSave).toHaveBeenLastCalledWith(expect.objectContaining({ skip_screens: ['Change password'] })))
    expect(screen.getByRole('button', { name: 'Remove Change password' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Remove Change password' }))
    await waitFor(() => expect(onSave).toHaveBeenLastCalledWith(expect.objectContaining({ skip_screens: [] })))
  })

  it('picks with the arrow keys and Enter, and says when nothing matches', async () => {
    const onSave = vi.fn(async () => {})
    const screens = [{ name: 'Loans dashboard' }, { name: 'Loan calculator' }] as unknown as ExplorerScreen[]
    render(<SummaryView run={runWith('POL-1')} screens={screens} onSave={onSave} onConfirm={vi.fn(async () => {})} />)
    const field = screen.getByLabelText(/Pages to leave out/)

    fireEvent.change(field, { target: { value: 'loan' } })
    fireEvent.keyDown(field, { key: 'ArrowDown' })
    expect(screen.getByRole('option', { name: 'Loan calculator' }).getAttribute('aria-selected')).toBe('true')
    fireEvent.keyDown(field, { key: 'Enter' })
    await waitFor(() => expect(onSave).toHaveBeenLastCalledWith(expect.objectContaining({ skip_screens: ['Loan calculator'] })))

    fireEvent.change(field, { target: { value: 'zzz' } })
    expect(screen.getByText('No page matches “zzz”')).toBeTruthy()
  })
})

