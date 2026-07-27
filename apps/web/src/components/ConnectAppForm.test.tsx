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
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    const select = screen.getByLabelText('Authentication method') as HTMLSelectElement
    expect(select.tagName).toBe('SELECT')
    expect(select.value).toBe('standard_login')
    expect(screen.getByLabelText('Username')).toBeTruthy()
    expect(screen.getByLabelText('Password')).toBeTruthy()
    expect(screen.queryByLabelText('API Key')).toBeNull()
  })

  it('offers exactly the confirmed 3-option auth method set, API Key and OAuth disabled pending backend support', () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    const select = screen.getByLabelText('Authentication method') as HTMLSelectElement
    const options = Array.from(select.options).map((o) => ({ value: o.value, disabled: o.disabled }))
    expect(options).toEqual([
      { value: 'standard_login', disabled: false },
      { value: 'api_key', disabled: true },
      { value: 'oauth_client_credentials', disabled: true },
    ])
  })

  it('swaps to the API Key field when the API Key method is selected', () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Authentication method'), {
      target: { value: 'api_key' },
    })

    expect(screen.queryByLabelText('Username')).toBeNull()
    expect(screen.queryByLabelText('Password')).toBeNull()
    expect(screen.getByLabelText('API Key')).toBeTruthy()
  })

  it('reveals no additional fields for OAuth Client Credentials (unconfirmed by the prototype)', () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Authentication method'), {
      target: { value: 'oauth_client_credentials' },
    })

    expect(screen.queryByLabelText('Username')).toBeNull()
    expect(screen.queryByLabelText('Password')).toBeNull()
    expect(screen.queryByLabelText('API Key')).toBeNull()
  })

  it('submits username/password when standard_login is selected (the default)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: '1', name: 'My App' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'qa-account' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'qa-password' } })
    fireEvent.click(screen.getByRole('button', { name: /Connect Application/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.auth_method).toBe('standard_login')
    expect(body.username).toBe('qa-account')
    expect(body.password).toBe('qa-password')
  })

  it('keeps the form on Connect App and shows the backend-provided inline error when the reachability check fails (FR-31)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: async () => ({ detail: "Could not reach this URL — check it's correct and reachable" }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'qa-account' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'qa-password' } })
    fireEvent.click(screen.getByRole('button', { name: /Connect Application/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe("Could not reach this URL — check it's correct and reachable")
    expect(onConnected).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Application name')).toBeTruthy()
  })

  it('calls onCancel when Cancel is clicked, matching prototype-v3.html Import screen', () => {
    const onCancel = vi.fn()
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
