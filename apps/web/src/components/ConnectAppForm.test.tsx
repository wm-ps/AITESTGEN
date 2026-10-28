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

// "Start discovery" now logs in with the entered credentials before creating
// the application (start + poll, like Regenerate/Auto-fill) — two extra
// fetches sit between Test connection and the create call.
const CHECK_STARTED = { ok: true, status: 202, json: async () => ({ check_id: 'check-1' }) }
const CHECK_VALID = { ok: true, status: 200, json: async () => ({ status: 'valid', detail: null }) }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ConnectAppForm', () => {
  it('shows Username/Password by default — sign-in starts on', () => {
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
      .mockResolvedValueOnce(CHECK_STARTED)
      .mockResolvedValueOnce(CHECK_VALID)
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: '1', name: 'My App' }) })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))
    const body = JSON.parse(fetchMock.mock.calls[3][1].body)
    expect(body.auth_method).toBe('standard_login')
    expect(body.username).toBe('qa-account')
    expect(body.password).toBe('qa-password')
  })

  it('defaults Autonomous exploration to checked and sends discovery_required true', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce(CHECK_STARTED)
      .mockResolvedValueOnce(CHECK_VALID)
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: '1', name: 'My App' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    expect((screen.getByLabelText('Autonomous exploration') as HTMLInputElement).checked).toBe(true)
    expect(screen.queryByRole('button', { name: /Add application/ })).toBeNull()

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))
    expect(JSON.parse(fetchMock.mock.calls[3][1].body).discovery_required).toBe(true)
  })

  it('relabels the submit button "Add application" and sends discovery_required false when unchecked', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: '1', name: 'My App' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fireEvent.click(screen.getByLabelText('Autonomous exploration'))
    expect(screen.queryByRole('button', { name: /Start exploration/ })).toBeNull()

    fillCommonFields()
    await passConnectionTest()
    fireEvent.click(screen.getByRole('button', { name: /Add application/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).discovery_required).toBe(false)
  })

  it('keeps requiring a tested connection when exploration is unchecked', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fireEvent.click(screen.getByLabelText('Autonomous exploration'))
    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Add application/ }))

    await screen.findByText('Test the connection above to enable Add application.')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(onConnected).not.toHaveBeenCalled()
  })

  it('hides the credentials and submits auth_method none when sign-in is toggled off', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: '1', name: 'My App' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    const toggle = screen.getByRole('switch', { name: 'This application requires sign-in' })
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.queryByLabelText('Username')).toBeNull()
    expect(screen.queryByLabelText('Password')).toBeNull()
    expect(screen.queryByLabelText('Login URL (optional)')).toBeNull()

    fireEvent.change(screen.getByLabelText('Application name'), { target: { value: 'My App' } })
    fireEvent.change(screen.getByLabelText('Deployed URL'), { target: { value: 'https://staging.example.com' } })
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const body = JSON.parse(fetchMock.mock.calls[1][1].body)
    expect(body.auth_method).toBe('none')
    expect(body.username).toBeUndefined()
    expect(body.password).toBeUndefined()
  })

  it('does not show the workspace-defaults note under Autonomous exploration', () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    expect(screen.queryByText(/workspace defaults/)).toBeNull()
  })

  it('keeps the form on Connect App and shows the backend-provided inline error when the reachability check fails (FR-31)', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce(CHECK_STARTED)
      .mockResolvedValueOnce(CHECK_VALID)
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
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe("Could not reach this URL — check it's correct and reachable")
    expect(onConnected).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Application name')).toBeTruthy()
  })

  it('looks like a normal, enabled button before the connection is ever tested', async () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fillCommonFields()
    const startButton = screen.getByRole('button', { name: /Start exploration/ })
    expect(startButton).not.toBeDisabled()
    expect(screen.queryByText('Test the connection above to enable Start exploration.')).toBeNull()
  })

  it('blocks Add application and shows a popover when the connection was never tested', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fireEvent.click(screen.getByLabelText('Autonomous exploration'))
    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Add application/ }))

    await screen.findByText('Test the connection above to enable Add application.')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(onConnected).not.toHaveBeenCalled()
  })

  it('blocks Add application when the URL is edited after a successful test connection', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fireEvent.click(screen.getByLabelText('Autonomous exploration'))
    fillCommonFields()
    await passConnectionTest()
    // Editing the URL after testing it invalidates that test — the field's
    // own value is what changed, not just re-typing the same one.
    fireEvent.change(screen.getByLabelText('Deployed URL'), { target: { value: 'https://staging.example.com/v2' } })
    fireEvent.click(screen.getByRole('button', { name: /Add application/ }))

    await screen.findByText('Test the connection above to enable Add application.')
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

    fireEvent.click(screen.getByLabelText('Autonomous exploration'))
    fireEvent.change(screen.getByLabelText('Deployed URL'), { target: { value: 'https://staging.example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    await screen.findByText('URL is reachable.')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/applications/test-connection'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('shows "Validating credentials" on the button while the login check runs', async () => {
    let resolveStatus: (value: unknown) => void = () => {}
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce(CHECK_STARTED)
      .mockReturnValueOnce(new Promise((resolve) => { resolveStatus = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await screen.findByText('Validating credentials')
    resolveStatus({ ok: true, status: 200, json: async () => ({ status: 'invalid', detail: null }) })
    await screen.findByText(/username or password is incorrect/i)
  })

  it('does not create the application and shows an inline message under the credentials when the login is invalid', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce(CHECK_STARTED)
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ status: 'invalid', detail: 'Invalid credentials' }) })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    const alert = await screen.findByText(
      'The username or password is incorrect. Enter valid credentials and click Start exploration again.',
    )
    expect(alert.getAttribute('role')).toBe('alert')
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(onConnected).not.toHaveBeenCalled()
    // The user can correct the credentials and retry: the message clears on edit.
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'fixed-password' } })
    expect(screen.queryByText(/username or password is incorrect/i)).toBeNull()
    expect(screen.getByRole('button', { name: /Start exploration/ })).not.toBeDisabled()
  })

  it('asks the user to validate again, without creating anything, when the login cannot be confirmed', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce(CHECK_STARTED)
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ status: 'uncertain', detail: null }) })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await screen.findByText("We couldn't confirm these credentials. Click Start exploration to validate again.")
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(onConnected).not.toHaveBeenCalled()
  })

  it('treats a failed login-check request (e.g. exploration worker unavailable) as "validate again"', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        json: async () => ({ detail: 'DISCOVERY_UNAVAILABLE' }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await screen.findByText(/couldn't confirm these credentials/i)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(onConnected).not.toHaveBeenCalled()
  })

  it('sends the entered credentials and Login URL to the login check', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce(CHECK_STARTED)
      .mockResolvedValueOnce(CHECK_VALID)
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: '1', name: 'My App' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.change(screen.getByLabelText('Login URL (optional)'), {
      target: { value: 'https://staging.example.com/login' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))
    expect(fetchMock.mock.calls[1][0]).toContain('/applications/verify-credentials')
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      url: 'https://staging.example.com',
      login_url: 'https://staging.example.com/login',
      username: 'qa-account',
      password: 'qa-password',
    })
    expect(fetchMock.mock.calls[2][0]).toContain('/applications/verify-credentials/check-1')
  })

  it('hides Test connection while exploration is on — Start exploration checks the URL itself', () => {
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'Test connection' })).toBeNull()
    fireEvent.click(screen.getByLabelText('Autonomous exploration'))
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeTruthy()
  })

  it('stops at an unreachable URL before the login check or create, and shows that message', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: false, detail: 'Could not reach this URL' }) })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await screen.findByText('Could not reach this URL')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(onConnected).not.toHaveBeenCalled()
  })

  it('stays on the form with a retry message when exploration cannot start, and adds nothing', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ reachable: true, detail: null }) })
      .mockResolvedValueOnce(CHECK_STARTED)
      .mockResolvedValueOnce(CHECK_VALID)
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        json: async () => ({ detail: 'DISCOVERY_UNAVAILABLE' }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const onConnected = vi.fn()
    render(<ConnectAppForm onConnected={onConnected} onCancel={vi.fn()} />)

    fillCommonFields()
    fireEvent.click(screen.getByRole('button', { name: /Start exploration/ }))

    await screen.findByText(
      "Exploration couldn't start, so the application was not added. Click Start exploration to try again.",
    )
    expect(onConnected).not.toHaveBeenCalled()
    expect((screen.getByLabelText('Application name') as HTMLInputElement).value).toBe('My App')
    expect(screen.getByRole('button', { name: /Start exploration/ })).not.toBeDisabled()
  })

  it('calls onCancel when Cancel is clicked', () => {
    const onCancel = vi.fn()
    render(<ConnectAppForm onConnected={vi.fn()} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
