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

// Start discovery is gated on a successful Test connection (see
// ConnectAppForm's `canStartDiscovery`) — every test that submits the form
// now has to actually pass through that gate first, same as a real user
// would.
async function passConnectionTest() {
  fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
  await screen.findByText('URL is reachable.')
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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: '1', name: 'My App' }) })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    await passConnectionTest()
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const body = JSON.parse(fetchMock.mock.calls[1][1].body)
    expect(body.auth_method).toBe('standard_login')
    expect(body.username).toBe('qa-account')
    expect(body.password).toBe('qa-password')
  })

  it('submits notes typed during onboarding so they reach create_application', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: '1', name: 'My App' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fillCommonFields()
    await passConnectionTest()
    fireEvent.click(screen.getByRole('button', { name: /Notes \(optional\)/ }))
    fireEvent.change(
      screen.getByPlaceholderText('Describe the primary purpose of the application and the outcomes it should deliver'),
      { target: { value: 'Manage clients, accounts and investments.' } },
    )
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const body = JSON.parse(fetchMock.mock.calls[1][1].body)
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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: '1', name: 'My App' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fillCommonFields()
    await passConnectionTest()
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const body = JSON.parse(fetchMock.mock.calls[1][1].body)
    expect(body.application_context).toEqual({
      business_goal: null,
      business_domain: null,
      business_rules: null,
      additional_context: null,
    })
  })

  it('keeps the form on Connect App and shows the backend-provided inline error when the reachability check fails (FR-31)', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        json: async () => ({ detail: "Could not reach this URL — check it's correct and reachable" }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    await passConnectionTest()
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe("Could not reach this URL — check it's correct and reachable")
    expect(onConnected).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Application name')).toBeTruthy()
  })

  it('looks like a normal, enabled button before the connection is ever tested', async () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fillCommonFields()
    const startButton = screen.getByRole('button', { name: /Start discovery/ })
    expect(startButton).not.toBeDisabled()
    expect(screen.queryByText('Test the connection above to enable Start discovery.')).toBeNull()
  })

  it('blocks Start discovery and shows a popover when the connection was never tested', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await screen.findByText('Test the connection above to enable Start discovery.')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(onConnected).not.toHaveBeenCalled()
  })

  it('blocks Start discovery when the URL is edited after a successful test connection', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    await passConnectionTest()
    // Editing the URL after testing it invalidates that test — the field's
    // own value is what changed, not just re-typing the same one.
    fireEvent.change(screen.getByLabelText('Deployed URL'), { target: { value: 'https://staging.example.com/v2' } })
    fireEvent.click(screen.getByRole('button', { name: /Start discovery/ }))

    await screen.findByText('Test the connection above to enable Start discovery.')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(onConnected).not.toHaveBeenCalled()
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
