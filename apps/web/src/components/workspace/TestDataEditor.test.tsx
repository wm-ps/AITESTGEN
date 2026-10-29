import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ScenarioRead } from '../../api'
import { TestDataEditor } from './TestSuiteTab'

function scenario(overrides: Partial<ScenarioRead>): ScenarioRead {
  return {
    id: 's1',
    journey_id: 'j1',
    journey_name: 'Recorded tests',
    test_case_number: 1,
    type: 'happy',
    name: 'Transfer',
    steps: [],
    expected_result: '',
    test_data: [{ name: 'Amount', mandatory: true, value: '5' }],
    test_data_complete: true,
    ...overrides,
  }
}

const NOTE = "Login details come from this application's settings."

describe('TestDataEditor', () => {
  it('explains hidden login fields and lists only the editable ones', () => {
    render(
      <TestDataEditor scenario={scenario({ has_login_fields: true })} onScenarioUpdated={() => {}} onDone={() => {}} />,
    )
    expect(screen.getByText(NOTE)).toBeTruthy()
    expect(screen.getByText('Amount')).toBeTruthy()
  })

  it('says nothing about login when the test has no login fields', () => {
    render(<TestDataEditor scenario={scenario({})} onScenarioUpdated={() => {}} onDone={() => {}} />)
    expect(screen.queryByText(NOTE)).toBeNull()
  })
})
