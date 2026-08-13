import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ImportProgress } from './ImportProgress'

describe('ImportProgress', () => {
  it('shows the shared generation-loader animation, without naming any internal stage or a progress bar', () => {
    render(<ImportProgress />)

    expect(screen.getByRole('status').textContent).toContain('Discovering journeys')
    expect(screen.queryByRole('progressbar')).toBeNull()
    for (const stageName of ['Initialization', 'Authentication', 'Discovery', 'Analysis']) {
      expect(screen.queryByText(stageName)).toBeNull()
    }
    expect(document.body.textContent).not.toMatch(/crawl|queue|fingerprint/i)
  })

  it('names the Application in the heading when applicationName is given', () => {
    render(<ImportProgress applicationName="Claims Processing" />)
    expect(screen.getByText('Discovering journeys in Claims Processing')).toBeTruthy()
  })

  it('omits the Application name from the heading when not given', () => {
    render(<ImportProgress />)
    expect(screen.getByText('Discovering journeys')).toBeTruthy()
  })
})
