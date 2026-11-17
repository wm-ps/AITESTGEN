import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Toast } from './Toast'

// The outside-click listener is registered a tick after mount.
const settle = () => act(() => { vi.advanceTimersByTime(1) })

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('Toast', () => {
  it('dismisses on a click outside it', () => {
    const onDismiss = vi.fn()
    render(<Toast message="Run started" onDismiss={onDismiss} />)
    settle()
    fireEvent.pointerDown(document.body)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('stays when the toast itself is clicked, and the × still dismisses', () => {
    const onDismiss = vi.fn()
    render(<Toast message="Run started" onDismiss={onDismiss} />)
    settle()
    fireEvent.pointerDown(screen.getByText('Run started'))
    expect(onDismiss).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('is not dismissed by the click that opened it', () => {
    const onDismiss = vi.fn()
    render(<Toast message="Run started" onDismiss={onDismiss} />)
    // Same tick as mount: the listener isn't registered yet.
    fireEvent.pointerDown(document.body)
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('does nothing on outside clicks when it has no onDismiss', () => {
    render(<Toast message="Heads up" />)
    settle()
    fireEvent.pointerDown(document.body)
    expect(screen.getByText('Heads up')).toBeInTheDocument()
  })

  it('stops listening once removed', () => {
    const onDismiss = vi.fn()
    const { unmount } = render(<Toast message="Run started" onDismiss={onDismiss} />)
    settle()
    unmount()
    fireEvent.pointerDown(document.body)
    expect(onDismiss).not.toHaveBeenCalled()
  })
})
