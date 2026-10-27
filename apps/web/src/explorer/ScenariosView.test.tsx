import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ScenariosView } from './ScenariosView'
import type { ExplorerRun, ExplorerTestCase } from './explorerApi'

const t = (over: Partial<ExplorerTestCase>) =>
  ({ id: over.title, status: 'proven', trust: 'standard', steps: [], expected: 'e', has_proof_video: false, ...over }) as ExplorerTestCase

describe('ScenariosView', () => {
  it('puts whole journeys first, in their own group, ahead of busier screens', () => {
    const tests = [
      t({ title: 'Claim review loads', kind: 'data_load', start_screen: 'Claim review' }),
      t({ title: 'Reference is required', kind: 'validation', start_screen: 'Claim review' }),
      t({ title: 'Report and submit a complete claim', kind: 'journey', start_screen: 'Claims support' }),
    ]
    render(<ScenariosView run={{ id: 'r1', status: 'tested' } as ExplorerRun} tests={tests} onOpenShot={vi.fn()} onVerdict={vi.fn()} />)
    const headings = screen.getAllByText(/^(Whole journeys|Claim review)$/).map((e) => e.textContent)
    expect(headings[0]).toBe('Whole journeys')
    expect(screen.getByText('Report and submit a complete claim')).toBeTruthy()  // first group opens by default
  })
})
