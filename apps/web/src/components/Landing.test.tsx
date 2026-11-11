import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Landing } from './Landing'

afterEach(cleanup)

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

  it('shows the thank-you message after the contact form is sent', () => {
    render(<Landing onNavigate={() => {}} onSignIn={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Connect with team/ }))
    expect(screen.getByRole('dialog', { name: "Let's connect" })).toBeTruthy()
    fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: 'Sam Lee' } })
    fireEvent.change(screen.getByLabelText(/Work Email/), { target: { value: 'sam@example.com' } })
    fireEvent.change(screen.getByLabelText(/Company/), { target: { value: 'Acme' } })
    fireEvent.change(screen.getByLabelText(/What are you interested in/), { target: { value: 'demo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Connect with our Team' }))
    expect(screen.getByText(/Someone from the team will be in touch/)).toBeTruthy()
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
