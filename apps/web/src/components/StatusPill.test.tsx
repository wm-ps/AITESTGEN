import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusPill } from './StatusPill'

describe('StatusPill', () => {
  it('shows Discovery in Progress with a spinning ring in signal color', () => {
    render(<StatusPill status="running" />)
    const pill = screen.getByText('Discovery in Progress')
    expect((pill as HTMLElement).style.color).toBe('var(--accent)')
    const dot = document.querySelector('[aria-hidden="true"]') as HTMLElement
    expect(dot.style.animation).toContain('aitg-spin')
  })

  it('shows Complete in good/green color with a static dot, not spinning', () => {
    render(<StatusPill status="complete" />)
    const pill = screen.getByText('Complete')
    expect((pill as HTMLElement).style.color).toBe('var(--good-strong)')
    const dot = document.querySelector('[aria-hidden="true"]') as HTMLElement
    expect(dot.style.animation).toBe('')
  })
})
