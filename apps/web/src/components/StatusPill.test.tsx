import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusPill } from './StatusPill'

describe('StatusPill', () => {
  it('shows Exploration in Progress with bouncing dots in signal color', () => {
    render(<StatusPill status="running" />)
    const pill = screen.getByText('Exploration in Progress')
    expect((pill as HTMLElement).style.color).toBe('var(--accent)')
    const dots = document.querySelector('[aria-hidden="true"]') as HTMLElement
    expect(dots.children).toHaveLength(3)
    expect((dots.children[0] as HTMLElement).style.animation).toContain('aitg-dot-bounce')
  })

  it('shows Complete in good/green color with a static dot, not spinning', () => {
    render(<StatusPill status="complete" />)
    const pill = screen.getByText('Complete')
    expect((pill as HTMLElement).style.color).toBe('var(--good-strong)')
    const dot = document.querySelector('[aria-hidden="true"]') as HTMLElement
    expect(dot.style.animation).toBe('')
  })
})
