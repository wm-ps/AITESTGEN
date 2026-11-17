import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthorPromptCard } from './AuthorPromptCard'
import { api } from '../../api'
import type { JourneyRead } from '../../api'
import { explorerApi } from '../../explorer/explorerApi'
import type { ExplorerRun } from '../../explorer/explorerApi'

afterEach(() => vi.restoreAllMocks())

const JOURNEYS = [{ id: 'j1', name: 'Create territory' }] as JourneyRead[]

describe('AuthorPromptCard', () => {
  it('adds the test cases to the existing journey chosen', async () => {
    vi.spyOn(api, 'listJourneys').mockResolvedValue(JOURNEYS)
    const start = vi.spyOn(explorerApi, 'startAuthoring').mockResolvedValue({ id: 'r1' } as ExplorerRun)
    const onStarted = vi.fn()
    render(<AuthorPromptCard applicationId="a1" onClose={vi.fn()} onStarted={onStarted} />)
    const button = screen.getByRole('button', { name: 'Start authoring' }) as HTMLButtonElement

    fireEvent.change(screen.getByLabelText('What to test'), { target: { value: '  Search policy POL-1  ' } })
    expect(button.disabled).toBe(true) // no journey chosen yet
    await screen.findByRole('option', { name: 'Create territory' })
    fireEvent.change(screen.getByLabelText('Journey'), { target: { value: 'j1' } })
    fireEvent.click(button)
    await waitFor(() => expect(onStarted).toHaveBeenCalledTimes(1))
    expect(start).toHaveBeenCalledWith('a1', 'Search policy POL-1', { journey_id: 'j1' })
  })

  it('creates a new journey by name', async () => {
    vi.spyOn(api, 'listJourneys').mockResolvedValue(JOURNEYS)
    const start = vi.spyOn(explorerApi, 'startAuthoring').mockResolvedValue({ id: 'r1' } as ExplorerRun)
    render(<AuthorPromptCard applicationId="a1" onClose={vi.fn()} onStarted={vi.fn()} />)
    await screen.findByRole('option', { name: 'Create territory' })
    fireEvent.change(screen.getByLabelText('Journey'), { target: { value: '__new__' } })
    fireEvent.change(screen.getByLabelText('What to test'), { target: { value: 'Search policy' } })
    const button = screen.getByRole('button', { name: 'Start authoring' }) as HTMLButtonElement
    expect(button.disabled).toBe(true) // the new journey has no name yet
    fireEvent.change(screen.getByLabelText('New journey name'), { target: { value: ' Policies ' } })
    fireEvent.click(button)
    await waitFor(() => expect(start).toHaveBeenCalledWith('a1', 'Search policy', { journey_name: 'Policies' }))
  })

  it('says why it could not start', async () => {
    vi.spyOn(api, 'listJourneys').mockResolvedValue([])
    vi.spyOn(explorerApi, 'startAuthoring').mockRejectedValue(new Error('Explorer is already running for this application'))
    const onStarted = vi.fn()
    render(<AuthorPromptCard applicationId="a1" onClose={vi.fn()} onStarted={onStarted} />)
    // No journeys yet: a new one is the only choice.
    fireEvent.change(await screen.findByLabelText('New journey name'), { target: { value: 'Policies' } })
    fireEvent.change(screen.getByLabelText('What to test'), { target: { value: 'Search policy' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start authoring' }))
    expect(await screen.findByText('Explorer is already running for this application')).toBeTruthy()
    expect(onStarted).not.toHaveBeenCalled()
  })
})
