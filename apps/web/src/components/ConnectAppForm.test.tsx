import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ConnectAppForm } from './ConnectAppForm'

function fillCommonFields() {
  fireEvent.change(screen.getByLabelText('Application name'), { target: { value: 'My App' } })
  fireEvent.change(screen.getByLabelText('Base URL'), {
    target: { value: 'https://staging.example.com' },
  })
  fireEvent.change(screen.getByLabelText('Environment'), { target: { value: 'staging' } })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ConnectAppForm', () => {
  it('defaults the Authentication method select to Username & Password with credential fields visible', () => {
    render(<ConnectAppForm onConnected={vi.fn()} />)

    const select = screen.getByLabelText('Authentication method') as HTMLSelectElement
    expect(select.tagName).toBe('SELECT')
    expect(select.value).toBe('standard_login')
    expect(screen.getByLabelText('Username')).toBeTruthy()
    expect(screen.getByLabelText('Password')).toBeTruthy()
    expect(screen.queryByLabelText('Session state (JSON)')).toBeNull()
  })

  it('swaps to the session-state field when SSO/MFA session reuse is selected', () => {
    render(<ConnectAppForm onConnected={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Authentication method'), {
      target: { value: 'sso_session_reuse' },
    })

    expect(screen.queryByLabelText('Username')).toBeNull()
    expect(screen.queryByLabelText('Password')).toBeNull()
    expect(screen.getByLabelText('Session state (JSON)')).toBeTruthy()
  })

  it('submits username/password when standard_login is selected (the default)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: '1', name: 'My App' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} />)

    fillCommonFields()
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'qa-account' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'qa-password' } })
    fireEvent.click(screen.getByRole('button', { name: /Connect Application/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.auth_method).toBe('standard_login')
    expect(body.username).toBe('qa-account')
    expect(body.password).toBe('qa-password')
    expect(body.session_state).toBeUndefined()
  })

  it('submits session_state when sso_session_reuse is selected', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: '1', name: 'My App' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} />)

    fillCommonFields()
    fireEvent.change(screen.getByLabelText('Authentication method'), {
      target: { value: 'sso_session_reuse' },
    })
    fireEvent.change(screen.getByLabelText('Session state (JSON)'), {
      target: { value: '{"cookies":[]}' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Connect Application/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.auth_method).toBe('sso_session_reuse')
    expect(body.session_state).toBe('{"cookies":[]}')
    expect(body.username).toBeUndefined()
    expect(body.password).toBeUndefined()
  })

  it('never claims the platform performs the SSO/MFA handshake itself', () => {
    render(<ConnectAppForm onConnected={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Authentication method'), {
      target: { value: 'sso_session_reuse' },
    })

    const bodyText = document.body.textContent ?? ''
    for (const claim of ['SAML', 'OAuth', 'OIDC', 'retrieves your MFA', 'logs you in via SSO']) {
      expect(bodyText).not.toContain(claim)
    }
  })
})
