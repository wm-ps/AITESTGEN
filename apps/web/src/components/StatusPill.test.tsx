import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusPill } from './StatusPill'

describe('StatusPill', () => {
  it('shows Running with a pulsing dot in signal color', () => {
    render(<StatusPill status="running" />)
    const pill = screen.getByText('Running')
    expect((pill as HTMLElement).style.color).toBe('var(--signal)')
    expect(document.querySelector('.status-pill-pulse-dot')).toBeTruthy()
  })

  it('shows Complete in good/green color with no pulsing dot', () => {
    render(<StatusPill status="complete" />)
    const pill = screen.getByText('Complete')
    expect((pill as HTMLElement).style.color).toBe('var(--good)')
    expect(document.querySelector('.status-pill-pulse-dot')).toBeNull()
  })
})
