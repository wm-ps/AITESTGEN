import { describe, expect, it } from 'vitest'
import { plainAction } from './ScreensView'

describe('plainAction', () => {
  it('drops icon wording and names a bare icon plainly', () => {
    expect(plainAction('Logout Icon Logout')).toBe('Logout')
    expect(plainAction('Icon')).toBe('an unlabelled button')
    expect(plainAction('Report an insurance claim →')).toBe('Report an insurance claim →')
    expect(plainAction(null)).toBe('Continue')
  })
})

describe('inFoundOrder', () => {
  it('keeps the found order but puts sign-in first', async () => {
    const { inFoundOrder } = await import('./ScreensView')
    const s = (name: string, view_kind: string) => ({ id: name, name, view_kind }) as Parameters<typeof inFoundOrder>[0][number]
    const ordered = inFoundOrder([s('Claims support', 'dashboard'), s('Claim safety check', 'wizard'), s('Agent login', 'login')])
    expect(ordered.map((x) => x.name)).toEqual(['Agent login', 'Claims support', 'Claim safety check'])
  })
})
