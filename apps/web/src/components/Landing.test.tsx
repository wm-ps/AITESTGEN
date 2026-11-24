import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from '../api'
import { Landing } from './Landing'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function fillContactForm() {
  fireEvent.click(screen.getByRole('button', { name: /Connect with our team/ }))
  fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: 'Sam Lee' } })
  fireEvent.change(screen.getByLabelText(/Work Email/), { target: { value: 'sam@example.com' } })
  fireEvent.change(screen.getByLabelText(/Company/), { target: { value: 'Acme' } })
  fireEvent.change(screen.getByLabelText(/What are you interested in/), { target: { value: 'demo' } })
}

describe('Landing', () => {
  it('calls onSignIn from the header Sign in button', () => {
    const onSignIn = vi.fn()
    render(<Landing onNavigate={() => {}} onSignIn={onSignIn} />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(onSignIn).toHaveBeenCalledOnce()
  })

  it('opens the demo video and closes it on Escape', () => {
    render(<Landing onNavigate={() => {}} onSignIn={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Watch a demo/ }))
    expect(screen.getByRole('dialog', { name: 'Vantage demo' })).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Vantage demo' })).toBeNull()
  })

  it('shows the thank-you message after the contact form is sent', async () => {
    const send = vi.spyOn(api, 'sendContactEnquiry').mockResolvedValue({ status: 'ok' })
    render(<Landing onNavigate={() => {}} onSignIn={() => {}} />)
    fillContactForm()
    expect(screen.getByRole('dialog', { name: "Let's connect" })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Connect with our Team' }))
    expect(await screen.findByRole('heading', { name: 'Thank you, Sam' })).toBeTruthy()
    expect(send).toHaveBeenCalledOnce()
  })

  it('replaces the form with a thank-you card that closes itself', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      vi.spyOn(api, 'sendContactEnquiry').mockResolvedValue({ status: 'ok' })
      render(<Landing onNavigate={() => {}} onSignIn={() => {}} />)
      fillContactForm()
      fireEvent.click(screen.getByRole('button', { name: 'Connect with our Team' }))
      const card = await screen.findByRole('dialog', { name: 'Thank you, Sam' })
      expect(card.textContent).toContain('Our team will reply to sam@example.com.')
      expect(screen.queryByText("Let's connect")).toBeNull()
      expect(screen.queryByText(/Tell us a little about your requirements/)).toBeNull()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000)
      })
      expect(screen.queryByRole('dialog', { name: 'Thank you, Sam' })).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps the contact form open on a backdrop click, closes it from its X', () => {
    render(<Landing onNavigate={() => {}} onSignIn={() => {}} />)
    fillContactForm()
    const dialog = screen.getByRole('dialog', { name: "Let's connect" })
    fireEvent.click(dialog)
    expect(screen.getByRole('dialog', { name: "Let's connect" })).toBeTruthy()
    expect((screen.getByLabelText(/Full Name/) as HTMLInputElement).value).toBe('Sam Lee')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog', { name: "Let's connect" })).toBeNull()
  })

  it('keeps the demo video open on a backdrop click, closes it from its X', () => {
    render(<Landing onNavigate={() => {}} onSignIn={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Watch a demo/ }))
    fireEvent.click(screen.getByRole('dialog', { name: 'Vantage demo' }))
    expect(screen.getByRole('dialog', { name: 'Vantage demo' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog', { name: 'Vantage demo' })).toBeNull()
  })

  it('shows Sending and ignores a second click while the enquiry is in flight', async () => {
    let resolve: (v: { status: string }) => void = () => {}
    const send = vi
      .spyOn(api, 'sendContactEnquiry')
      .mockReturnValue(new Promise((r) => (resolve = r)))
    render(<Landing onNavigate={() => {}} onSignIn={() => {}} />)
    fillContactForm()
    const submit = screen.getByRole('button', { name: 'Connect with our Team' })
    fireEvent.click(submit)
    expect(await screen.findByRole('button', { name: /Sending/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Sending/ }).hasAttribute('disabled')).toBe(true)
    fireEvent.submit(screen.getByRole('button', { name: /Sending/ }).closest('form')!)
    expect(send).toHaveBeenCalledOnce()
    // No thank-you until the API answers.
    expect(screen.queryByRole('heading', { name: 'Thank you, Sam' })).toBeNull()
    resolve({ status: 'ok' })
    expect(await screen.findByRole('heading', { name: 'Thank you, Sam' })).toBeTruthy()
  })

  it('keeps the entered details and shows an error when sending fails', async () => {
    vi.spyOn(api, 'sendContactEnquiry').mockRejectedValue(new ApiError("We couldn't send your message.", 502))
    render(<Landing onNavigate={() => {}} onSignIn={() => {}} />)
    fillContactForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connect with our Team' }))
    expect((await screen.findByRole('alert')).textContent).toBe("We couldn't send your message. Please try again.")
    expect(screen.queryByRole('heading', { name: 'Thank you, Sam' })).toBeNull()
    expect((screen.getByLabelText(/Full Name/) as HTMLInputElement).value).toBe('Sam Lee')
    expect((screen.getByLabelText(/Work Email/) as HTMLInputElement).value).toBe('sam@example.com')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Connect with our Team' })).toBeTruthy())
  })

  it('tells the visitor to wait when they hit the rate limit', async () => {
    vi.spyOn(api, 'sendContactEnquiry').mockRejectedValue(new ApiError('Too many enquiries.', 429))
    render(<Landing onNavigate={() => {}} onSignIn={() => {}} />)
    fillContactForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connect with our Team' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Too many enquiries. Please try again later.')
  })
})

describe('Landing header nav', () => {
  afterEach(cleanup)

  it('navigates to the Product page from the header', () => {
    const onNavigate = vi.fn()
    render(<Landing onNavigate={onNavigate} onSignIn={() => {}} />)
    fireEvent.click(screen.getByRole('link', { name: 'Product' }))
    expect(onNavigate).toHaveBeenCalledWith('product')
  })
})
