import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { RecordAndPlay } from './RecordAndPlay'

vi.mock('../hooks/useRecordingControlSocket', () => ({
  useRecordingControlSocket: () => ({
    stage: 'recording',
    reconnecting: false,
    errorMessage: null,
    saved: null,
    stopWarning: null,
    sendStop: () => {},
  }),
}))

function renderRecord(requiresSignIn: boolean) {
  render(
    <RecordAndPlay
      applicationId="a1"
      applicationName="Shop"
      applicationUrl="https://shop.example.com"
      requiresSignIn={requiresSignIn}
      onSaved={() => {}}
      onCancelled={() => {}}
    />,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('RecordAndPlay', () => {
  it('shows no recording-mode choice for an app without sign-in and records logged out', async () => {
    const create = vi
      .spyOn(api, 'createRecordingSession')
      .mockResolvedValue({ id: 'r1', vnc_ws_url: 'ws://v', control_ws_url: 'ws://c' })
    vi.spyOn(window, 'open').mockReturnValue(null)
    renderRecord(false)

    expect(screen.queryByRole('radiogroup', { name: 'Recording mode' })).toBeNull()
    fireEvent.change(screen.getByPlaceholderText('Enter a name for this flow'), { target: { value: 'Browse' } })
    fireEvent.click(screen.getByRole('button', { name: 'Record a flow' }))

    await waitFor(() => expect(create).toHaveBeenCalledWith('a1', 'logged_out', 'Browse'))
  })

  it('keeps both recording modes for an app with sign-in', () => {
    renderRecord(true)
    expect(screen.getByRole('radiogroup', { name: 'Recording mode' })).toBeTruthy()
    expect(screen.getByText('Record a login flow')).toBeTruthy()
    expect(screen.getByText('Record an authenticated flow')).toBeTruthy()
  })
})
