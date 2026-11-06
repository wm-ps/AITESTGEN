import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../../api'
import { SuiteSelect } from './SuiteSelect'
import { summary } from './fixtures'

afterEach(() => vi.restoreAllMocks())

describe('SuiteSelect', () => {
  it('lists "All test cases" first, then the suites with their test case counts', async () => {
    vi.spyOn(api, 'listCollections').mockResolvedValue([
      summary({ id: 'c1', name: 'Smoke', test_case_count: 3 }),
      summary({ id: 'c2', name: 'Regression', test_case_count: 1 }),
    ])
    render(<SuiteSelect applicationId="app-1" value={null} onChange={vi.fn()} />)

    const select = (await screen.findByLabelText('Test suite')) as HTMLSelectElement
    expect(Array.from(select.options).map((o) => o.text)).toEqual([
      'All test cases',
      'Smoke (3 test cases)',
      'Regression (1 test case)',
    ])
  })

  it('reports the chosen suite, null for all test cases', async () => {
    vi.spyOn(api, 'listCollections').mockResolvedValue([summary({ id: 'c1', name: 'Smoke' })])
    const onChange = vi.fn()
    render(<SuiteSelect applicationId="app-1" value={null} onChange={onChange} />)
    const select = await screen.findByLabelText('Test suite')

    fireEvent.change(select, { target: { value: 'c1' } })
    expect(onChange).toHaveBeenLastCalledWith('c1')
    fireEvent.change(select, { target: { value: '__all_test_cases__' } })
    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('does not let a suite with nothing runnable be picked', async () => {
    vi.spyOn(api, 'listCollections').mockResolvedValue([summary({ id: 'c1', name: 'Empty', test_case_count: 0 })])
    render(<SuiteSelect applicationId="app-1" value={null} onChange={vi.fn()} />)

    const select = (await screen.findByLabelText('Test suite')) as HTMLSelectElement
    expect(select.options[1].disabled).toBe(true)
  })

  it('renders nothing when the application has no suites', async () => {
    const list = vi.spyOn(api, 'listCollections').mockResolvedValue([])
    const { container } = render(<SuiteSelect applicationId="app-1" value={null} onChange={vi.fn()} />)

    await waitFor(() => expect(list).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the suites cannot be loaded', async () => {
    const list = vi.spyOn(api, 'listCollections').mockRejectedValue(new Error('offline'))
    const { container } = render(<SuiteSelect applicationId="app-1" value={null} onChange={vi.fn()} />)

    await waitFor(() => expect(list).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})
