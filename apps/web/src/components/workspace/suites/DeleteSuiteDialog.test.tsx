import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, SUITE_HAS_SCHEDULES, SUITE_RUN_IN_PROGRESS, api, type ScheduleRead } from '../../../api'
import { DeleteSuiteDialog } from './DeleteSuiteDialog'
import { summary } from './fixtures'

afterEach(() => vi.restoreAllMocks())

describe('DeleteSuiteDialog', () => {
  it('without runs it is a plain confirm and deletes without removing runs', async () => {
    const del = vi.spyOn(api, 'deleteCollection').mockResolvedValue(undefined)
    const onDeleted = vi.fn()
    render(<DeleteSuiteDialog applicationId="app-1" suite={summary({ run_count: 0 })} onClose={vi.fn()} onDeleted={onDeleted} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete suite' }))
    await waitFor(() => expect(onDeleted).toHaveBeenCalled())
    expect(del).toHaveBeenCalledWith('c1', false)
  })

  it('with runs it warns they are removed too, and only deletes them after confirming', async () => {
    const del = vi.spyOn(api, 'deleteCollection').mockResolvedValue(undefined)
    const onDeleted = vi.fn()
    render(<DeleteSuiteDialog applicationId="app-1" suite={summary({ run_count: 3 })} onClose={vi.fn()} onDeleted={onDeleted} />)
    expect(screen.getByText(/3 runs\. Deleting it also permanently removes those runs/)).toBeInTheDocument()
    expect(del).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Delete suite and runs' }))
    await waitFor(() => expect(onDeleted).toHaveBeenCalled())
    expect(del).toHaveBeenCalledWith('c1', true)
  })

  it('Cancel deletes nothing', () => {
    const del = vi.spyOn(api, 'deleteCollection').mockResolvedValue(undefined)
    const onClose = vi.fn()
    render(<DeleteSuiteDialog applicationId="app-1" suite={summary({ run_count: 3 })} onClose={onClose} onDeleted={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
    expect(del).not.toHaveBeenCalled()
  })

  it('explains when a run is still in progress and stays open', async () => {
    vi.spyOn(api, 'deleteCollection').mockRejectedValue(new ApiError(SUITE_RUN_IN_PROGRESS, 409))
    const onDeleted = vi.fn()
    render(<DeleteSuiteDialog applicationId="app-1" suite={summary({ run_count: 1 })} onClose={vi.fn()} onDeleted={onDeleted} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete suite and runs' }))
    await screen.findByText(/still in progress/)
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('names the schedules that use the suite when delete is refused', async () => {
    vi.spyOn(api, 'deleteCollection').mockRejectedValue(new ApiError(SUITE_HAS_SCHEDULES, 409))
    vi.spyOn(api, 'listSchedules').mockResolvedValue([
      { id: 's1', name: 'Nightly smoke', test_collection_id: 'c1' } as ScheduleRead,
      { id: 's2', name: 'Unrelated', test_collection_id: null } as ScheduleRead,
    ])
    const onDeleted = vi.fn()
    render(<DeleteSuiteDialog applicationId="app-1" suite={summary({ run_count: 0 })} onClose={vi.fn()} onDeleted={onDeleted} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete suite' }))
    await screen.findByText(/used by Nightly smoke\. Change or delete that schedule first/)
    expect(screen.queryByText(/Unrelated/)).toBeNull()
    expect(onDeleted).not.toHaveBeenCalled()
  })
})
