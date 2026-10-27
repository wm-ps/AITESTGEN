import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { HealthView } from './HealthView'
import { explorerApi, type ExplorerHealthIssue, type ExplorerQuestion } from './explorerApi'

vi.mock('./explorerApi', async (orig) => {
  const real = await orig<typeof import('./explorerApi')>()
  return { ...real, explorerApi: { ...real.explorerApi, falseAlarm: vi.fn(async () => undefined), answer: vi.fn(async () => ({})) } }
})

const issue: ExplorerHealthIssue = {
  id: 'i1',
  kind: 'looks_wrong',
  severity: 'medium',
  title: 'Date of birth shows several formats',
  detail: 'A date field should show one clear date.',
  url: '/x',
  occurrences: 1,
  shot_id: 's1',
}
const question = { id: 'q1', kind: 'rule', status: 'open', shot_id: 's1' } as ExplorerQuestion

describe('HealthView', () => {
  it('shows every finding with its answers at once, and False alarm closes it', async () => {
    const onAnswered = vi.fn(async () => {})
    render(<HealthView issues={[issue]} questions={[question]} onAnswered={onAnswered} onOpenShot={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Things that look wrong/ }))

    // No expanding needed: detail and every answer are already there.
    expect(screen.getByText('A date field should show one clear date.')).toBeTruthy()
    expect(screen.getByRole('button', { name: "It's a bug" })).toBeTruthy()
    expect(screen.getByRole('button', { name: "It's correct" })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'False alarm' }))
    await waitFor(() => expect(onAnswered).toHaveBeenCalled())
    expect(explorerApi.falseAlarm).toHaveBeenCalledWith('i1')
  })
})

describe('Things that look wrong: CSV download', () => {
  it('writes every finding as Excel-ready CSV, defusing formulas', async () => {
    const { bugsCsv } = await import('./HealthView')
    const csv = bugsCsv(
      [issue, { ...issue, id: 'i2', title: '=HYPERLINK("http://evil")', detail: 'Say "hi"', shot_id: null }],
      [question],
    )
    expect(csv.startsWith('\ufeff')).toBe(true) // Excel reads it as UTF-8
    const [header, first, second] = csv.slice(1).split('\r\n')
    expect(header).toBe('"Type","Severity","Needs your answer","Title","Details","Page","Times seen"')
    expect(first).toContain('"Looks wrong","medium","Yes","Date of birth shows several formats"')
    expect(first).not.toContain('/explorer/shots/')
    expect(second).toContain(`"'=HYPERLINK(""http://evil"")"`) // never runs as a formula
    expect(second).toContain('"Say ""hi"""')
  })

  it('offers the download only when there is something to download', () => {
    const { unmount } = render(<HealthView issues={[issue]} questions={[]} onAnswered={vi.fn(async () => {})} onOpenShot={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Download CSV/ })).toBeTruthy()
    unmount()
    render(<HealthView issues={[]} questions={[]} onAnswered={vi.fn(async () => {})} onOpenShot={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Download CSV/ })).toBeNull()
  })
})
