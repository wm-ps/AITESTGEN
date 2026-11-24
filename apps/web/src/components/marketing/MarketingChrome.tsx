import { useEffect, useRef, useState, type ReactNode } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCheck, faChevronDown, faPlay, faRightToBracket, faXmark } from '@fortawesome/free-solid-svg-icons'
import { faComments } from '@fortawesome/free-regular-svg-icons'
import { ApiError, api, type ContactEnquiry } from '../../api'
import { LoadingDots } from '../LoadingDots'

// Shared header, footer and dialogs for the signed-out pages (Landing at `/`,
// Product at `/product`). App owns the routing; these only call onNavigate.

export type PublicPage = 'landing' | 'product'

export const TEAL = '#0F766E'

const DEMO_VIDEO = '/demo/app-demo.mp4'

const NAV: { page: PublicPage; label: string; href: string }[] = [
  { page: 'landing', label: 'Home', href: '/' },
  { page: 'product', label: 'Product', href: '/product' },
]

// Landing's header is translucent over its background art; Product's sticks
// to the top of a long scrolling page.
const HEADER_VARIANT = {
  landing: {
    position: 'relative',
    borderBottom: '1px solid rgba(15,118,110,0.12)',
    background: 'rgba(250,250,251,0.55)',
    backdropFilter: 'blur(8px)',
    WebkitBackdropFilter: 'blur(8px)',
  },
  product: { position: 'sticky', top: 0, zIndex: 50, borderBottom: '1px solid #E5E6E9', background: 'rgba(250,250,251,0.94)' },
} as const

export const MAX_WIDTH: Record<PublicPage, number> = { landing: 1240, product: 1320 }
const GUTTER: Record<PublicPage, string> = { landing: 'clamp(20px,4vw,32px)', product: 'clamp(20px,4vw,40px)' }

export function MarketingHeader({
  current,
  onNavigate,
  onSignIn,
}: {
  current: PublicPage
  onNavigate: (page: PublicPage) => void
  onSignIn: () => void
}) {
  return (
    <header style={HEADER_VARIANT[current]}>
      <nav
        aria-label="Main"
        style={{
          maxWidth: MAX_WIDTH[current],
          margin: '0 auto',
          height: 64,
          padding: `0 ${GUTTER[current]}`,
          display: 'grid',
          gridTemplateColumns: '1fr auto 1fr',
          alignItems: 'center',
          gap: 24,
        }}
      >
        <a
          href="/"
          aria-label="Vantage home"
          onClick={(e) => {
            e.preventDefault()
            onNavigate('landing')
          }}
          style={{ justifySelf: 'start', minHeight: 44, display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none' }}
        >
          <svg width="28" height="26" viewBox="0 0 28 26" aria-hidden="true" style={{ flex: 'none' }}>
            <path d="M3 12.5 L14 3.5 L25 12.5" fill="none" stroke={TEAL} strokeWidth="4.6" strokeLinejoin="miter" strokeLinecap="butt" />
            <path d="M3 23 L14 14 L25 23" fill="none" stroke={TEAL} strokeWidth="4.6" strokeLinejoin="miter" strokeLinecap="butt" />
          </svg>
          <span className="marketing-wordmark" style={{ fontSize: 19, fontWeight: 700, letterSpacing: '0.16em', color: TEAL, lineHeight: 1 }}>
            VANTAGE
          </span>
        </a>
        <span style={{ display: 'flex', alignItems: 'center', gap: 'clamp(16px,3vw,32px)' }}>
          {NAV.map((item) => (
            <a
              key={item.page}
              href={item.href}
              aria-current={item.page === current ? 'page' : undefined}
              className={item.page === current ? 'marketing-nav marketing-nav-current' : 'marketing-nav'}
              onClick={(e) => {
                e.preventDefault()
                onNavigate(item.page)
              }}
            >
              {item.label}
            </a>
          ))}
        </span>
        <button
          type="button"
          className="landing-btn landing-btn-teal"
          onClick={onSignIn}
          style={{ justifySelf: 'end', height: 44, gap: 9, padding: '0 18px', borderRadius: 10, fontSize: 14.5 }}
        >
          <FontAwesomeIcon icon={faRightToBracket} style={{ fontSize: 12 }} />
          Sign in
        </button>
      </nav>
    </header>
  )
}

export function MarketingFooter({ current }: { current: PublicPage }) {
  return (
    <footer style={{ borderTop: current === 'landing' ? '1px solid rgba(15,118,110,0.12)' : '1px solid #E5E6E9' }}>
      <div
        style={{
          maxWidth: MAX_WIDTH[current],
          margin: '0 auto',
          padding: `${current === 'landing' ? 16 : 22}px ${GUTTER[current]}`,
          fontSize: 13,
          color: current === 'landing' ? '#232329' : '#5C5C66',
        }}
      >
        © 2026 Vantage. An initiative of Omnewave.
      </div>
    </footer>
  )
}

// The two calls to action, drawn the same on every signed-out page. `onTeal`
// is for a teal band, where the teal demo button turns white.
export function WatchDemoButton({ onClick, onTeal = false }: { onClick: () => void; onTeal?: boolean }) {
  return (
    <button
      type="button"
      className={`landing-btn landing-btn-lift ${onTeal ? 'product-btn-white' : 'landing-btn-teal'}`}
      onClick={onClick}
      style={{ height: 54, gap: 12, padding: '0 24px 0 9px', borderRadius: 12, fontSize: 15.5 }}
    >
      <span
        style={{
          width: 36,
          height: 36,
          borderRadius: 9,
          background: onTeal ? 'rgba(15,118,110,0.1)' : 'rgba(255,255,255,0.16)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <FontAwesomeIcon icon={faPlay} style={{ fontSize: 12, marginLeft: 2 }} />
      </span>
      Watch a demo
    </button>
  )
}

export function ConnectTeamButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="landing-btn landing-btn-ink landing-btn-lift"
      onClick={onClick}
      style={{ height: 54, gap: 10, padding: '0 24px', borderRadius: 12, fontSize: 15.5 }}
    >
      <FontAwesomeIcon icon={faComments} style={{ fontSize: 14 }} />
      Connect with our team
    </button>
  )
}

// Demo / contact dialog state, closed together by Escape (or each one's X).
export function useMarketingDialogs() {
  const [demoOpen, setDemoOpen] = useState(false)
  const [contactOpen, setContactOpen] = useState(false)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setDemoOpen(false)
        setContactOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return {
    demoOpen,
    contactOpen,
    openDemo: () => setDemoOpen(true),
    openContact: () => setContactOpen(true),
    closeAll: () => {
      setDemoOpen(false)
      setContactOpen(false)
    },
  }
}

// No backdrop click: these close only from their X or Escape, so a stray
// click can't throw away what the visitor typed or was watching.
function MarketingDialog({ label, labelledBy, maxWidth, children }: {
  label?: string
  labelledBy?: string
  maxWidth: number
  children: ReactNode
}) {
  return (
    <div role="dialog" aria-modal="true" aria-label={label} aria-labelledby={labelledBy} className="landing-backdrop" style={{ overflowY: 'auto' }}>
      <div className="landing-modal" style={{ maxWidth, overflow: 'hidden' }}>
        {children}
      </div>
    </div>
  )
}

function CloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label="Close"
      onClick={onClick}
      className="marketing-close"
      style={{ width: 32, height: 32, flex: 'none', border: 0, borderRadius: 7, cursor: 'pointer' }}
    >
      <FontAwesomeIcon icon={faXmark} />
    </button>
  )
}

export function DemoDialog({ onClose }: { onClose: () => void }) {
  return (
    <MarketingDialog label="Vantage demo" maxWidth={1040}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 18px', borderBottom: '1px solid #E5E6E9' }}>
        <span style={{ fontSize: 15, fontWeight: 600, color: '#16161A' }}>Vantage demo</span>
        <CloseButton onClick={onClose} />
      </div>
      <div style={{ position: 'relative', aspectRatio: '16/9', background: '#EDEEF0' }}>
        <video
          src={DEMO_VIDEO}
          title="Vantage demo video"
          controls
          autoPlay
          playsInline
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', background: '#000' }}
        />
      </div>
    </MarketingDialog>
  )
}

const INTERESTS: [string, string][] = [
  ['demo', 'Product demo'],
  ['pilot', 'Pilot or proof of concept'],
  ['pricing', 'Pricing and licensing'],
  ['enterprise', 'Enterprise deployment'],
  ['partnership', 'Partnership'],
  ['other', 'Something else'],
]

function FieldLabel({ text, required }: { text: string; required?: boolean }) {
  return (
    <span>
      {text}
      {required && (
        <span style={{ color: TEAL }} aria-hidden="true">
          {' *'}
        </span>
      )}
    </span>
  )
}

// The "Connect with our Team" enquiry form, the same on Landing and Product.
// How long the thank-you card stays before closing itself.
const SENT_CLOSE_MS = 5000

const EMPTY_ENQUIRY: ContactEnquiry = { name: '', email: '', company: '', role: '', interest: '', message: '', website: '' }

export function ContactDialog({ onClose }: { onClose: () => void }) {
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Controlled, so a failed send keeps everything the visitor typed.
  const [form, setForm] = useState<ContactEnquiry>(EMPTY_ENQUIRY)
  const interest = form.interest

  // Latest onClose in a ref, so a parent re-render (new inline onClose)
  // doesn't restart the auto-close countdown.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  useEffect(() => {
    if (!sent) return
    const timer = setTimeout(() => onCloseRef.current(), SENT_CLOSE_MS)
    return () => clearTimeout(timer)
  }, [sent])

  function field(key: keyof ContactEnquiry) {
    return {
      name: key,
      value: form[key],
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
        setForm((f) => ({ ...f, [key]: e.target.value })),
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (sending) return
    setSending(true)
    setError(null)
    try {
      await api.sendContactEnquiry(form)
      setSent(true)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? 'Too many enquiries. Please try again later.'
          : "We couldn't send your message. Please try again.",
      )
    } finally {
      setSending(false)
    }
  }

  if (sent) {
    const firstName = form.name.split(/\s+/)[0]
    return (
      <MarketingDialog key="sent" labelledBy="marketing-contact-sent-title" maxWidth={440}>
        <div style={{ position: 'relative', padding: '40px 32px 34px', textAlign: 'center' }}>
          <span style={{ position: 'absolute', top: 14, right: 14 }}>
            <CloseButton onClick={onClose} />
          </span>
          <span
            style={{
              width: 52,
              height: 52,
              margin: '0 auto 20px',
              borderRadius: 100,
              background: 'rgba(15,118,110,0.10)',
              color: TEAL,
              fontSize: 20,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <FontAwesomeIcon icon={faCheck} />
          </span>
          <h2 id="marketing-contact-sent-title" style={{ margin: 0, fontSize: 21, fontWeight: 600, letterSpacing: '-0.02em', color: '#16161A' }}>
            Thank you, {firstName}
          </h2>
          <p style={{ margin: '10px auto 0', maxWidth: 320, fontSize: 14.5, lineHeight: 1.55, color: '#484851', textWrap: 'pretty' }}>
            Your enquiry has been sent. Our team will reply to <span style={{ color: '#16161A', fontWeight: 500, overflowWrap: 'anywhere' }}>{form.email}</span>.
          </p>
        </div>
        {/* Shrinks over SENT_CLOSE_MS so the auto-close isn't a surprise. */}
        <div aria-hidden="true" className="marketing-sent-timer" style={{ animationDuration: `${SENT_CLOSE_MS}ms` }} />
      </MarketingDialog>
    )
  }

  return (
    <MarketingDialog labelledBy="marketing-contact-title" maxWidth={560}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, padding: '26px 28px 0' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <h2 id="marketing-contact-title" style={{ margin: 0, fontSize: 24, fontWeight: 600, letterSpacing: '-0.025em', color: '#16161A' }}>
            Let's connect
          </h2>
          <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.55, color: '#484851', textWrap: 'pretty' }}>
            Tell us a little about your requirements. Our team will get in touch to explore how Vantage can help.
          </p>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <form onSubmit={handleSubmit} style={{ padding: '22px 28px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(min(100%,220px),1fr))', gap: 16 }}>
          <label className="landing-label">
            <FieldLabel text="Full Name" required />
            <input {...field('name')} required maxLength={100} autoComplete="name" placeholder="Enter your full name" className="landing-input marketing-field" />
          </label>
          <label className="landing-label">
            <FieldLabel text="Work Email" required />
            <input {...field('email')} type="email" required maxLength={254} autoComplete="email" placeholder="Enter your work email" className="landing-input marketing-field" />
          </label>
          <label className="landing-label">
            <FieldLabel text="Company / Organization" required />
            <input {...field('company')} required maxLength={150} autoComplete="organization" placeholder="Enter your company name" className="landing-input marketing-field" />
          </label>
          <label className="landing-label">
            <FieldLabel text="Job Title / Role" />
            <input {...field('role')} maxLength={100} autoComplete="organization-title" placeholder="Enter your job title or role" className="landing-input marketing-field" />
          </label>
        </div>
        <label className="landing-label">
          <FieldLabel text="What are you interested in?" required />
          <span style={{ position: 'relative', display: 'block' }}>
            <select
              {...field('interest')}
              required
              className="landing-input marketing-field"
              style={{ width: '100%', paddingRight: 40, appearance: 'none', cursor: 'pointer', color: interest ? '#16161A' : '#9C9CA6' }}
            >
              <option value="" disabled>
                Select an area of interest
              </option>
              {INTERESTS.map(([value, label]) => (
                <option key={value} value={value} style={{ color: '#16161A' }}>
                  {label}
                </option>
              ))}
            </select>
            <FontAwesomeIcon
              icon={faChevronDown}
              aria-hidden="true"
              style={{ position: 'absolute', right: 15, top: '50%', transform: 'translateY(-50%)', fontSize: 11, color: '#5C5C66', pointerEvents: 'none' }}
            />
          </span>
        </label>
        <label className="landing-label">
          <FieldLabel text="How can we help?" />
          <textarea
            {...field('message')}
            rows={3}
            maxLength={2000}
            placeholder="Tell us briefly about your testing challenges or requirements"
            className="landing-input marketing-field"
            style={{ height: 'auto', minHeight: 96, padding: '12px 14px', lineHeight: 1.5, resize: 'vertical' }}
          />
        </label>
        {/* Honeypot: off-screen and skipped by keyboard and screen readers, so only bots fill it. */}
        <div aria-hidden="true" style={{ position: 'absolute', left: -10000, width: 1, height: 1, overflow: 'hidden' }}>
          <label>
            Website
            <input {...field('website')} type="text" tabIndex={-1} autoComplete="off" />
          </label>
        </div>
        {error && (
          <p role="alert" style={{ margin: 0, fontSize: 13.5, color: '#B42318' }}>
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={sending}
          className="landing-btn landing-btn-teal"
          style={{ marginTop: 4, height: 50, borderRadius: 10, fontSize: 15, justifyContent: 'center', opacity: sending ? 0.75 : 1 }}
        >
          {sending ? <LoadingDots label="Sending" /> : 'Connect with our Team'}
        </button>
        <p style={{ margin: 0, textAlign: 'center', fontSize: 12.5, color: '#5C5C66' }}>Your information will only be used to respond to your enquiry.</p>
      </form>
    </MarketingDialog>
  )
}
