import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type EnvironmentRead, type ScheduleRead } from '../../api'
import { RunSuiteButton } from '../workspace/RunSuiteButton'
import { ScheduleDialog } from '../workspace/ScheduleDialog'
import { DownloadEnvironmentDialog } from './DownloadEnvironmentDialog'
import { EnvironmentSelect } from './EnvironmentSelect'
import { EnvironmentsProvider, type EnvironmentsValue } from './EnvironmentsContext'

const DEFAULT_ENV: EnvironmentRead = {
  id: null,
  name: 'production',
  url: 'https://prod.example.com',
  login_url: null,
  is_default: true,
  auth_method: 'standard_login',
  username: 'qa',
}
const UAT: EnvironmentRead = { ...DEFAULT_ENV, id: 'env-uat', name: 'UAT', url: 'https://uat.example.com', is_default: false }

function withEnvironments(ui: React.ReactNode, overrides: Partial<EnvironmentsValue> = {}) {
  const value: EnvironmentsValue = {
    environments: [DEFAULT_ENV, UAT],
    refresh: vi.fn(async () => {}),
    requestAdd: vi.fn(),
    canAdd: true,
    ...overrides,
  }
  render(<EnvironmentsProvider value={value}>{ui}</EnvironmentsProvider>)
  return value
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('EnvironmentSelect', () => {
  it('lists the default first, then the extras, then "Add new environment"', () => {
    withEnvironments(<EnvironmentSelect value={null} onChange={vi.fn()} />)

    const options = Array.from((screen.getByLabelText('Environment') as HTMLSelectElement).options).map((o) => o.text)
    expect(options).toEqual(['Production', 'UAT', '+ Add new environment'])
  })

  it('reports the chosen environment, null for the default', () => {
    const onChange = vi.fn()
    withEnvironments(<EnvironmentSelect value={null} onChange={onChange} />)
    const select = screen.getByLabelText('Environment')

    fireEvent.change(select, { target: { value: 'env-uat' } })
    expect(onChange).toHaveBeenLastCalledWith('env-uat')
    fireEvent.change(select, { target: { value: '__default_environment__' } })
    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('opens the Add dialog and selects what it adds', () => {
    const onChange = vi.fn()
    const value = withEnvironments(<EnvironmentSelect value={null} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText('Environment'), { target: { value: '__add_new_environment__' } })

    expect(onChange).not.toHaveBeenCalled()
    const onAdded = (value.requestAdd as ReturnType<typeof vi.fn>).mock.calls[0][0]
    onAdded({ ...UAT, id: 'env-new' })
    expect(onChange).toHaveBeenCalledWith('env-new')
  })

  it('offers no Add option when environments cannot be added', () => {
    withEnvironments(<EnvironmentSelect value={null} onChange={vi.fn()} />, { canAdd: false })

    const options = Array.from((screen.getByLabelText('Environment') as HTMLSelectElement).options).map((o) => o.text)
    expect(options).not.toContain('+ Add new environment')
  })

  it('renders nothing outside a workspace or before environments load', () => {
    const { container } = render(<EnvironmentSelect value={null} onChange={vi.fn()} />)
    expect(container.firstChild).toBeNull()
    withEnvironments(<EnvironmentSelect value={null} onChange={vi.fn()} />, { environments: [] })
    expect(screen.queryByLabelText('Environment')).toBeNull()
  })
})

describe('Run tests dialog', () => {
  function openDialog(onFullSuite = vi.fn(), onOpenJourneysDialog = vi.fn()) {
    withEnvironments(
      <RunSuiteButton running={false} onFullSuite={onFullSuite} onOpenJourneysDialog={onOpenJourneysDialog} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Run' }))
    return { onFullSuite, onOpenJourneysDialog }
  }

  it('runs on the default environment unless another is chosen', () => {
    const { onFullSuite } = openDialog()

    expect((screen.getByLabelText('Run on environment') as HTMLSelectElement).value).toBe('__default_environment__')
    fireEvent.click(screen.getByRole('button', { name: /All test cases/ }))

    expect(onFullSuite).toHaveBeenCalledWith(null)
  })

  it('runs the whole suite on the chosen environment', () => {
    const { onFullSuite } = openDialog()

    fireEvent.change(screen.getByLabelText('Run on environment'), { target: { value: 'env-uat' } })
    fireEvent.click(screen.getByRole('button', { name: /All test cases/ }))

    expect(onFullSuite).toHaveBeenCalledWith('env-uat')
  })

  it('carries the chosen environment into the selective run', () => {
    const { onOpenJourneysDialog } = openDialog()

    fireEvent.change(screen.getByLabelText('Run on environment'), { target: { value: 'env-uat' } })
    fireEvent.click(screen.getByRole('button', { name: /Selective run/ }))

    expect(onOpenJourneysDialog).toHaveBeenCalledWith('env-uat')
  })
})

describe('Download project dialog', () => {
  it('downloads the project for the default environment unless another is chosen', async () => {
    const download = vi.spyOn(api, 'downloadTestSuiteProject').mockResolvedValue(undefined)
    const onClose = vi.fn()
    withEnvironments(<DownloadEnvironmentDialog applicationId="app-1" onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Download' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(download).toHaveBeenCalledWith('app-1', undefined)
  })

  it('downloads the project for the chosen environment', async () => {
    const download = vi.spyOn(api, 'downloadTestSuiteProject').mockResolvedValue(undefined)
    withEnvironments(<DownloadEnvironmentDialog applicationId="app-1" onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Environment'), { target: { value: 'env-uat' } })
    fireEvent.click(screen.getByRole('button', { name: 'Download' }))

    await waitFor(() => expect(download).toHaveBeenCalledWith('app-1', 'env-uat'))
  })

  it('says what is written into the config, without claiming credentials are', () => {
    withEnvironments(<DownloadEnvironmentDialog applicationId="app-1" onClose={vi.fn()} />)

    expect(screen.getByText(/base URL and login URL are written into the config/)).toBeTruthy()
    expect(screen.queryByText(/sign-in details are written/i)).toBeNull()
  })

  it('stays open with a message when the download fails', async () => {
    vi.spyOn(api, 'downloadTestSuiteProject').mockRejectedValue(new Error('boom'))
    const onClose = vi.fn()
    withEnvironments(<DownloadEnvironmentDialog applicationId="app-1" onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Download' }))

    expect((await screen.findByRole('alert')).textContent).toBe('Could not download the project. Try again.')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('does nothing when cancelled', () => {
    const download = vi.spyOn(api, 'downloadTestSuiteProject').mockResolvedValue(undefined)
    const onClose = vi.fn()
    withEnvironments(<DownloadEnvironmentDialog applicationId="app-1" onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalled()
    expect(download).not.toHaveBeenCalled()
  })
})

describe('Schedule dialog', () => {
  const SCHEDULE: ScheduleRead = {
    id: 'sched-1',
    name: 'Nightly',
    cadence_type: 'daily',
    hour: 2,
    minute: 0,
    days_of_week: [],
    day_of_month: null,
    cron_expression: null,
    time_zone: 'UTC',
    enabled: true,
    cadence_label: 'Daily at 02:00',
    next_run_at: null,
    created_by_name: null,
    created_at: '2026-01-01T00:00:00Z',
    environment_id: 'env-uat',
    environment_name: 'UAT',
  }

  it('creates a schedule on the chosen environment', async () => {
    const create = vi.spyOn(api, 'createSchedule').mockResolvedValue(SCHEDULE)
    withEnvironments(<ScheduleDialog applicationId="app-1" initial={null} onClose={vi.fn()} onSaved={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText('Enter a name for this schedule'), { target: { value: 'Nightly' } })
    fireEvent.change(screen.getByLabelText('Environment'), { target: { value: 'env-uat' } })
    fireEvent.click(screen.getByRole('button', { name: /Create schedule/ }))

    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][1]).toMatchObject({ name: 'Nightly', environment_id: 'env-uat' })
  })

  it('leaves environment_id out when the default environment is kept', async () => {
    const create = vi.spyOn(api, 'createSchedule').mockResolvedValue(SCHEDULE)
    withEnvironments(<ScheduleDialog applicationId="app-1" initial={null} onClose={vi.fn()} onSaved={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText('Enter a name for this schedule'), { target: { value: 'Nightly' } })
    fireEvent.click(screen.getByRole('button', { name: /Create schedule/ }))

    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][1]).not.toHaveProperty('environment_id')
  })

  it('prefills the schedule’s environment and leaves it alone when untouched', async () => {
    const update = vi.spyOn(api, 'updateSchedule').mockResolvedValue(SCHEDULE)
    withEnvironments(<ScheduleDialog applicationId="app-1" initial={SCHEDULE} onClose={vi.fn()} onSaved={vi.fn()} />)

    expect((screen.getByLabelText('Environment') as HTMLSelectElement).value).toBe('env-uat')
    fireEvent.click(screen.getByRole('button', { name: /Save changes/ }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update.mock.calls[0][1]).not.toHaveProperty('environment_id')
  })

  it('moves a schedule back to the default environment with an explicit null', async () => {
    const update = vi.spyOn(api, 'updateSchedule').mockResolvedValue({ ...SCHEDULE, environment_id: null })
    withEnvironments(<ScheduleDialog applicationId="app-1" initial={SCHEDULE} onClose={vi.fn()} onSaved={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Environment'), { target: { value: '__default_environment__' } })
    fireEvent.click(screen.getByRole('button', { name: /Save changes/ }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update.mock.calls[0][1]).toHaveProperty('environment_id', null)
  })
})
