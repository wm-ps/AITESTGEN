import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from '../../../api'
import { PermissionsProvider } from '../../../PermissionsContext'
import { TestSuitesPage } from './TestSuitesPage'
import { detail, summary } from './fixtures'

const SMOKE = summary({ id: 'c1', name: 'Smoke', test_case_count: 4, unavailable_count: 1, run_count: 4 })
const REGRESSION = summary({ id: 'c2', name: 'Regression', test_case_count: 7, run_count: 7 })

const now = new Date().toISOString()
const SMOKE_DETAIL = detail({
  id: 'c1',
  name: 'Smoke',
  test_case_count: 4,
  journey_count: 3,
  run_count: 4,
  available: [
    { scenario_id: 's1', name: 'Sign in with valid credentials', journey_name: 'Authentication' },
    { scenario_id: 's2', name: 'Submit a claim', journey_name: 'Claim submission' },
    { scenario_id: 's3', name: 'Renew a policy and pay the premium', journey_name: 'Policy renewal and payment' },
    { scenario_id: 's4', name: 'Sign out', journey_name: 'Authentication' },
  ],
  unavailable: [{ scenario_id: 'gone', name: 'Apply a promo code at renewal' }],
  recent_runs: [
    { id: 'r4', run_number: 4, suite_name: 'Smoke', status: 'completed', created_at: now, total: 4, passed: 3, failed: 1 },
    { id: 'r3', run_number: 3, suite_name: 'Smoke', status: 'completed', created_at: now, total: 4, passed: 4, failed: 0 },
    { id: 'r2', run_number: 2, suite_name: 'Smoke', status: 'running', created_at: now, total: 4, passed: 0, failed: 0 },
  ],
})

function mockApi(suites = [SMOKE, REGRESSION]) {
  vi.spyOn(api, 'listCollections').mockResolvedValue(suites)
  vi.spyOn(api, 'getCollection').mockImplementation(async (id: string) =>
    id === 'c1' ? SMOKE_DETAIL : detail({ id, name: 'Regression', test_case_count: 7 }),
  )
}

async function openCasesTab() {
  // The tabs render from the list before the suite's detail has loaded; wait
  // for the detail (its first run) so the click cannot land too early.
  await screen.findByText('Run 4')
  fireEvent.click(screen.getByRole('tab', { name: /Test cases \(4\)/ }))
}

afterEach(() => vi.restoreAllMocks())

describe('TestSuitesPage', () => {
  it('lists suites with counts and opens the first one on Run history', async () => {
    mockApi()
    render(<TestSuitesPage applicationId="app-1" />)
    await screen.findByText('2 Suites')
    expect(screen.getByText('4 test cases · 4 runs')).toBeInTheDocument()
    expect(screen.getByText('7 test cases · 7 runs')).toBeInTheDocument()
    expect(await screen.findByText('4 test cases across 3 journeys · 1 unavailable')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Run history (4)', selected: true })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Test cases (4)', selected: false })).toBeInTheDocument()
  })

  it('marks a suite with unavailable test cases by an info icon whose tooltip says how many', async () => {
    mockApi()
    render(<TestSuitesPage applicationId="app-1" />)
    await screen.findByText('2 Suites')
    const info = screen.getByRole('img', { name: '1 unavailable' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.mouseEnter(info)
    expect(screen.getByRole('tooltip')).toHaveTextContent('1 unavailable')
    fireEvent.mouseLeave(info)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    // a suite with nothing unavailable has no icon
    expect(screen.getAllByRole('img', { name: /unavailable/ })).toHaveLength(1)
  })

  it('Run history lists each run with its result and no suite chip', async () => {
    mockApi()
    render(<TestSuitesPage applicationId="app-1" />)
    await screen.findByText('Run 4')
    expect(screen.getByText('1 of 4 failed')).toBeInTheDocument()
    expect(screen.getByText('4 of 4 passed')).toBeInTheDocument()
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText('Showing the latest 3 of 4 runs.')).toBeInTheDocument()
  })

  it('Test cases tab groups by journey, opening only the first, and journeys expand on click', async () => {
    mockApi()
    render(<TestSuitesPage applicationId="app-1" />)
    await openCasesTab()
    expect(screen.getByRole('button', { name: /Authentication/ })).toBeInTheDocument()
    expect(screen.getByText('2 test cases')).toBeInTheDocument()
    expect(screen.getByText('Sign in with valid credentials')).toBeInTheDocument()
    expect(screen.queryByText('Submit a claim')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Claim submission/ }))
    expect(screen.getByText('Submit a claim')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Authentication/ }))
    expect(screen.queryByText('Sign in with valid credentials')).not.toBeInTheDocument()
  })

  it('search narrows within the suite and opens every matching journey', async () => {
    mockApi()
    render(<TestSuitesPage applicationId="app-1" />)
    await openCasesTab()
    fireEvent.change(screen.getByLabelText('Search test cases in this suite'), { target: { value: 'renew' } })
    expect(screen.getByText('Renew a policy and pay the premium')).toBeInTheDocument()
    expect(screen.queryByText('Sign in with valid credentials')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Search test cases in this suite'), { target: { value: 'zzz' } })
    expect(screen.getByText('No test cases match your search.')).toBeInTheDocument()
  })

  it('the journey filter shows only that journey', async () => {
    mockApi()
    render(<TestSuitesPage applicationId="app-1" />)
    await openCasesTab()
    fireEvent.change(screen.getByLabelText('Filter by journey'), { target: { value: 'Claim submission' } })
    expect(screen.queryByRole('button', { name: /Authentication/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Claim submission/ })).toBeInTheDocument()
  })

  it('Remove on a test case row takes just that one out of the suite', async () => {
    mockApi()
    const change = vi.spyOn(api, 'changeCollectionMembers').mockResolvedValue(SMOKE)
    render(<TestSuitesPage applicationId="app-1" />)
    await openCasesTab()
    fireEvent.click(screen.getByRole('button', { name: 'Remove Sign in with valid credentials' }))
    await waitFor(() => expect(change).toHaveBeenCalledWith('c1', { remove: ['s1'] }))
  })

  it('shows unavailable test cases struck through below the list; Remove and Remove all clear them', async () => {
    mockApi()
    const change = vi.spyOn(api, 'changeCollectionMembers').mockResolvedValue(SMOKE)
    render(<TestSuitesPage applicationId="app-1" />)
    await openCasesTab()
    const card = await screen.findByRole('region', { name: 'Unavailable test cases' })
    expect(within(card).getByText('1 test case no longer available')).toBeInTheDocument()
    expect(within(card).getByText('Apply a promo code at renewal')).toBeInTheDocument()
    expect(within(card).getByText('No longer available')).toBeInTheDocument()

    fireEvent.click(within(card).getByRole('button', { name: 'Remove Apply a promo code at renewal' }))
    await waitFor(() => expect(change).toHaveBeenCalledWith('c1', { remove: ['gone'] }))

    fireEvent.click(within(card).getByRole('button', { name: 'Remove all' }))
    await waitFor(() => expect(change).toHaveBeenLastCalledWith('c1', { remove: ['gone'] }))
  })

  it('an unavailable card is not shown on the Run history tab', async () => {
    mockApi()
    render(<TestSuitesPage applicationId="app-1" />)
    await screen.findByText('Run 4')
    expect(screen.queryByText('1 test case no longer available')).not.toBeInTheDocument()
  })

  it('selecting another suite loads its details and goes back to Run history', async () => {
    mockApi()
    render(<TestSuitesPage applicationId="app-1" />)
    await openCasesTab()
    fireEvent.click(screen.getByText('Regression'))
    await waitFor(() => expect(api.getCollection).toHaveBeenCalledWith('c2'))
    expect(await screen.findByRole('tab', { name: /Run history/, selected: true })).toBeInTheDocument()
  })

  it('a suite never run says so', async () => {
    mockApi()
    render(<TestSuitesPage applicationId="app-1" />)
    await screen.findByText('2 Suites')
    fireEvent.click(screen.getByText('Regression'))
    await screen.findByText('This suite has not been run yet.')
  })

  it('has an empty state with a New suite button and no description line', async () => {
    mockApi([])
    render(<TestSuitesPage applicationId="app-1" />)
    await screen.findByText('No test suites yet')
    expect(screen.getByRole('button', { name: /New suite/ })).toBeInTheDocument()
    expect(screen.queryByText(/Group test cases into reusable sets/)).not.toBeInTheDocument()
  })

  it('New suite creates the suite and opens Select test cases for it', async () => {
    mockApi([])
    const created = summary({ id: 'c9', name: 'Payments', test_case_count: 0 })
    vi.spyOn(api, 'createCollection').mockResolvedValue(created)
    vi.spyOn(api, 'listCollectionCases').mockResolvedValue([])
    render(<TestSuitesPage applicationId="app-1" />)
    await screen.findByText('No test suites yet')
    vi.mocked(api.listCollections).mockResolvedValue([created])
    vi.mocked(api.getCollection).mockResolvedValue(detail({ id: 'c9', name: 'Payments' }))

    fireEvent.click(screen.getByRole('button', { name: /New suite/ }))
    fireEvent.change(screen.getByPlaceholderText('Enter the suite name'), { target: { value: 'Payments' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create suite' }))

    await screen.findByText('Select test cases')
    expect(api.createCollection).toHaveBeenCalledWith('app-1', 'Payments')
    expect(screen.getByText('Suite: Payments')).toBeInTheDocument()
  })

  it('a duplicate name is reported in the dialog', async () => {
    mockApi([])
    vi.spyOn(api, 'createCollection').mockRejectedValue(new ApiError('COLLECTION_NAME_TAKEN', 409))
    render(<TestSuitesPage applicationId="app-1" />)
    await screen.findByText('No test suites yet')
    fireEvent.click(screen.getByRole('button', { name: /New suite/ }))
    fireEvent.change(screen.getByPlaceholderText('Enter the suite name'), { target: { value: 'Smoke' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create suite' }))
    await screen.findByText('A suite with this name already exists')
  })

  it('a viewer sees suites but none of the controls that change them', async () => {
    mockApi()
    render(
      <PermissionsProvider value="viewer">
        <TestSuitesPage applicationId="app-1" />
      </PermissionsProvider>,
    )
    await screen.findByText('Run 4')
    expect(screen.queryByRole('button', { name: /New suite/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Manage test cases' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'More options' })).not.toBeInTheDocument()

    await openCasesTab()
    expect(screen.queryByRole('button', { name: /^Remove/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove all' })).not.toBeInTheDocument()
  })
})
