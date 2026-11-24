import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { Product } from './Product'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Product', () => {
  it('renders every section with Product marked as the current page', () => {
    render(<Product onNavigate={() => {}} onSignIn={() => {}} />)
    expect(screen.getByRole('heading', { level: 1, name: /Rethink Software Testing/ })).toBeTruthy()
    expect(screen.getByRole('heading', { name: "Traditional Testing Shouldn't Slow Down Innovation." })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'One Platform. Every Stage of Testing.' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Designed for Teams That Care About Quality.' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Product' }).getAttribute('aria-current')).toBe('page')
  })

  it('goes Home and to Sign in from the header', () => {
    const onNavigate = vi.fn()
    const onSignIn = vi.fn()
    render(<Product onNavigate={onNavigate} onSignIn={onSignIn} />)
    fireEvent.click(screen.getByRole('link', { name: 'Home' }))
    expect(onNavigate).toHaveBeenCalledWith('landing')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(onSignIn).toHaveBeenCalledOnce()
  })

  it('opens the demo video and the contact form from the call to action', () => {
    render(<Product onNavigate={() => {}} onSignIn={() => {}} />)
    fireEvent.click(screen.getAllByRole('button', { name: /Watch a demo/ })[0])
    expect(screen.getByRole('dialog', { name: 'Vantage demo' })).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    fireEvent.click(screen.getAllByRole('button', { name: 'Connect with our team' })[0])
    expect(screen.getByRole('dialog', { name: "Let's connect" })).toBeTruthy()
  })

  it('collects the full enquiry and thanks the user once sent', async () => {
    const send = vi.spyOn(api, 'sendContactEnquiry').mockResolvedValue({ status: 'ok' })
    render(<Product onNavigate={() => {}} onSignIn={() => {}} />)
    fireEvent.click(screen.getAllByRole('button', { name: 'Connect with our team' })[0])
    fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: 'Sam Lee' } })
    fireEvent.change(screen.getByLabelText(/Work Email/), { target: { value: 'sam@example.com' } })
    fireEvent.change(screen.getByLabelText(/Company/), { target: { value: 'Acme' } })
    fireEvent.change(screen.getByLabelText(/What are you interested in/), { target: { value: 'pilot' } })
    fireEvent.click(screen.getByRole('button', { name: 'Connect with our Team' }))
    expect(await screen.findByRole('heading', { name: 'Thank you, Sam' })).toBeTruthy()
    expect(send).toHaveBeenCalledWith({
      name: 'Sam Lee',
      email: 'sam@example.com',
      company: 'Acme',
      role: '',
      interest: 'pilot',
      message: '',
      website: '',
    })
  })
})
