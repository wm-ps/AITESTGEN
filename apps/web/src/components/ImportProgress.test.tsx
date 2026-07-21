import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ImportProgress } from './ImportProgress'

describe('ImportProgress', () => {
  // Percentage reflects the stage that just finished, not the current
  // stage's own target — see the comment in ImportProgress.tsx. No internal
  // stage name (Initialization/Authentication/Discovery/Analysis) is shown.
  it.each([
    ['initializing', 0],
    ['authenticating', 10],
    ['discovering', 25],
    ['analyzing', 75],
  ] as const)('renders %s at %d%%, without naming the stage', (stage, percent) => {
    const { container } = render(<ImportProgress stage={stage} />)

    expect(screen.getByText(`${percent}%`)).toBeTruthy()
    for (const stageName of ['Initialization', 'Authentication', 'Discovery', 'Analysis']) {
      expect(screen.queryByText(stageName)).toBeNull()
    }
    expect(container.textContent).not.toMatch(/crawl|queue|fingerprint/i)
  })

  it('falls back to 0% when stage is null', () => {
    render(<ImportProgress stage={null} />)
    expect(screen.getByText('0%')).toBeTruthy()
  })

  it('names the Application in the heading when applicationName is given', () => {
    render(<ImportProgress stage="discovering" applicationName="Claims Processing" />)
    expect(screen.getByText('Discovering journeys in Claims Processing')).toBeTruthy()
  })

  it('omits the Application name from the heading when not given', () => {
    render(<ImportProgress stage="discovering" />)
    expect(screen.getByText('Discovering journeys')).toBeTruthy()
  })
})
