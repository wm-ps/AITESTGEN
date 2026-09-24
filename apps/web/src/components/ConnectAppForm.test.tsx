import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ConnectAppForm } from './ConnectAppForm'

function fillCommonFields() {
  fireEvent.change(screen.getByLabelText('Application name'), { target: { value: 'My App' } })
  fireEvent.change(screen.getByLabelText('Deployed URL'), {
    target: { value: 'https://staging.example.com' },
  })
  fireEvent.change(screen.getByLabelText('Environment'), { target: { value: 'staging' } })
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'qa-account' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'qa-password' } })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ConnectAppForm', () => {
  it('always shows Username/Password — sign-in is required for every application today', () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    expect(screen.getByLabelText('Username')).toBeTruthy()
    expect(screen.getByLabelText('Password')).toBeTruthy()
  })

  it('offers Staging/Production/QA plus a free-text Other environment', () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    const select = screen.getByLabelText('Environment') as HTMLSelectElement
    const options = Array.from(select.options).map((o) => o.value)
    expect(options).toEqual(['staging', 'production', 'qa', 'other'])

    fireEvent.change(select, { target: { value: 'other' } })
    expect(screen.getByLabelText('Custom environment')).toBeTruthy()
  })

  it('submits with auth_method always standard_login', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: '1', name: 'My App' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.auth_method).toBe('standard_login')
    expect(body.username).toBe('qa-account')
    expect(body.password).toBe('qa-password')
  })

  it('submits notes typed during onboarding so they reach create_application', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: '1', name: 'My App' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Notes \(optional\)/ }))
    fireEvent.change(
      screen.getByPlaceholderText('Describe the primary purpose of the application and the outcomes it should deliver'),
      { target: { value: 'Manage clients, accounts and investments.' } },
    )
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.application_context).toMatchObject({
      business_goal: 'Manage clients, accounts and investments.',
    })
  })

  it('keeps Notes collapsed by default and preserves typed text across collapse/expand', () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    expect(
      screen.queryByPlaceholderText('Describe the primary purpose of the application and the outcomes it should deliver'),
    ).toBeNull()

    const toggle = screen.getByRole('button', { name: /Notes \(optional\)/ })
    fireEvent.click(toggle)
    fireEvent.change(
      screen.getByPlaceholderText('Describe the primary purpose of the application and the outcomes it should deliver'),
      { target: { value: 'Manage clients, accounts and investments.' } },
    )

    fireEvent.click(toggle)
    expect(
      screen.queryByPlaceholderText('Describe the primary purpose of the application and the outcomes it should deliver'),
    ).toBeNull()

    fireEvent.click(toggle)
    expect(
      screen.getByPlaceholderText('Describe the primary purpose of the application and the outcomes it should deliver'),
    ).toHaveValue('Manage clients, accounts and investments.')
  })

  it('submits application_context as all-null when no notes were typed', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: '1', name: 'My App' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.application_context).toEqual({
      business_goal: null,
      business_domain: null,
      business_rules: null,
      additional_context: null,
    })
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
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe("Could not reach this URL — check it's correct and reachable")
    expect(onConnected).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Application name')).toBeTruthy()
  })

  it('tests the Deployed URL reachability without submitting the form', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ reachable: true, detail: null }),
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Deployed URL'), { target: { value: 'https://staging.example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    await screen.findByText('URL is reachable.')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/applications/test-connection'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('calls onCancel when Cancel is clicked', () => {
    const onCancel = vi.fn()
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
