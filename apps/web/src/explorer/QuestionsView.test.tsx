import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QuestionCard } from './QuestionsView'
import { SummaryView } from './SummaryView'
import { explorerApi, type ExplorerQuestion, type ExplorerRun } from './explorerApi'

vi.mock('./explorerApi', async (orig) => {
  const real = await orig<typeof import('./explorerApi')>()
  return { ...real, explorerApi: { ...real.explorerApi, answer: vi.fn(async () => ({})) } }
})

const base: ExplorerQuestion = {
  id: 'q1',
  kind: 'data',
  question: 'Which claim type should I use?',
  why: null,
  options: ['Auto collision', 'Property damage'],
  shot_id: null,
  status: 'open',
  answer: null,
  answered_at: null,
  created_at: '2026-10-19T08:30:00Z',
  mission_title: null,
}

describe('QuestionCard', () => {
  it('offers Other with a text box next to the choices', async () => {
    render(<QuestionCard question={base} onAnswered={vi.fn(async () => {})} onOpenShot={vi.fn()} />)
    expect(screen.queryByLabelText('Your answer')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Other' }))
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'Both' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(explorerApi.answer).toHaveBeenCalledWith('q1', 'Both'))
  })

  it('shows the text box straight away when there are no choices', () => {
    render(<QuestionCard question={{ ...base, options: [] }} onAnswered={vi.fn(async () => {})} onOpenShot={vi.fn()} />)
    expect(screen.getByLabelText('Your answer')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Other' })).toBeNull()
  })
})

describe('SummaryView questions', () => {
  it('lets you answer with Other and saves your own words', async () => {
    const run = {
      id: 'r1',
      status: 'awaiting_confirmation',
      brief_confirmed_at: null,
      brief: { app_name: 'FNOL', questions_for_you: [{ question: 'Who files claims?', options: ['Customers', 'Agents'] }] },
    } as unknown as ExplorerRun
    const onSave = vi.fn(async () => {})
    render(<SummaryView run={run} screens={[]} onSave={onSave} onConfirm={vi.fn(async () => {})} />)
    fireEvent.click(screen.getByRole('button', { name: 'Other' }))
    fireEvent.change(screen.getByLabelText('Your answer to: Who files claims?'), { target: { value: 'Both' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0][0]).toMatchObject({ questions_for_you: [{ answer: 'Both' }] })
  })
})
