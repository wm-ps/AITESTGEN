import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthorPromptCard } from './AuthorPromptCard'
import { explorerApi } from '../../explorer/explorerApi'
import type { ExplorerRun } from '../../explorer/explorerApi'

afterEach(() => vi.restoreAllMocks())

describe('AuthorPromptCard', () => {
  it('starts an authoring run with the request and hands over to Explorer', async () => {
    const start = vi.spyOn(explorerApi, 'startAuthoring').mockResolvedValue({ id: 'r1' } as ExplorerRun)
    const onStarted = vi.fn()
    render(<AuthorPromptCard applicationId="a1" onClose={vi.fn()} onStarted={onStarted} />)
    const button = screen.getByRole('button', { name: 'Start authoring' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)

    fireEvent.change(screen.getByLabelText('What to test'), { target: { value: '  Search policy POL-1  ' } })
    fireEvent.click(button)
    await waitFor(() => expect(onStarted).toHaveBeenCalledTimes(1))
    expect(start).toHaveBeenCalledWith('a1', 'Search policy POL-1')
  })

  it('says why it could not start', async () => {
    vi.spyOn(explorerApi, 'startAuthoring').mockRejectedValue(new Error('Explorer is already running for this application'))
    const onStarted = vi.fn()
    render(<AuthorPromptCard applicationId="a1" onClose={vi.fn()} onStarted={onStarted} />)
    fireEvent.change(screen.getByLabelText('What to test'), { target: { value: 'Search policy' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start authoring' }))
    expect(await screen.findByText('Explorer is already running for this application')).toBeTruthy()
    expect(onStarted).not.toHaveBeenCalled()
  })
})
