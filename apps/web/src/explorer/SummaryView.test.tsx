import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SummaryView } from './SummaryView'
import type { ExplorerRun } from './explorerApi'

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
})
