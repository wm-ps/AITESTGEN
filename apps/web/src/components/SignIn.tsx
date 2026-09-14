import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowLeft, faArrowRight } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type UserRead } from '../api'
import { OmnewaveBrand } from './Brand'
import { LoadingDots } from './LoadingDots'
import { PasswordInput } from './PasswordInput'
// Full reference mock (logo + headline + laptop screenshot already baked
// in) — rendered with object-fit: contain so the whole image is always
// visible, unscaled/uncropped, at any viewport size or aspect ratio.
import signInLeftPanel from '../assets/signin-left-panel.png'

// ponytail: hardcoded on per explicit request — enabled in every build,
// prod included. Clicking the logo (or the "Sign in" heading) fills the
// seeded dev user's credentials (see seed_dev_data.py / dev-start scripts)
// but still leaves the user to submit the form themselves, so the real
// sign-in flow is untouched. If this ever needs to be off in prod,
// reintroduce a VITE_ENABLE_DEV_LOGIN build-time env check instead of this
// constant.
const DEV_LOGIN_ENABLED = true
const DEV_CREDENTIALS = { email: 'dev@example.com', password: 'devpassword123' }

export function SignIn({ onSignedIn }: { onSignedIn: (user: UserRead) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [mode, setMode] = useState<'signin' | 'forgot'>('signin')
  const [resetSent, setResetSent] = useState(false)

  function handleDevAutofill() {
    if (!DEV_LOGIN_ENABLED) return
    setEmail(DEV_CREDENTIALS.email)
    setPassword(DEV_CREDENTIALS.password)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const user = await api.login({ email, password })
      onSignedIn(user)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sign in failed.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleForgotSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.forgotPassword({ email })
      setResetSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send reset link.')
    } finally {
      setSubmitting(false)
    }
  }

  function handleBackToSignIn() {
    setMode('signin')
    setError(null)
    setResetSent(false)
  }

  return (
    <main
      style={{
        // 100vh (large viewport height) overshoots the real visible screen on mobile/
        // browsers with a collapsible chrome bar, pushing this section's bottom off-
        // screen and forcing a page scroll. 100svh (small viewport height) matches
        // what's actually visible right now, same as #root's min-height in index.css.
        height: '100svh',
        width: '100%',
        display: 'flex',
        position: 'relative',
        overflow: 'hidden',
        boxSizing: 'border-box',
        background: '#fff',
      }}
    >
      <section
        style={{
          flex: '0 1 53%',
          minWidth: 0,
          height: '100%',
          position: 'relative',
          overflow: 'hidden',
          boxSizing: 'border-box',
          background: '#F1F4F8',
        }}
      >
        <img
          src={signInLeftPanel}
          alt="Vantage: test smarter, release with confidence. Workspace overview shown open on a laptop."
          // cover always fills the panel edge-to-edge (no gap, guaranteed by the CSS
          // spec regardless of source resolution) but this image's aspect ratio
          // (1.23:1) is close enough to the panel's own that SOME edge always gets
          // cropped depending on the viewport — object-position anchors that crop to
          // the bottom-right (mug/plant/laptop edge), protecting the brand-critical
          // logo + headline in the top-left instead of splitting the crop evenly.
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'left top' }}
        />
      </section>

      <section
        style={{
          flex: '0 1 47%',
          minWidth: 0,
          height: '100%',
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: 'clamp(48px, 14vh, 160px) 56px 32px',
          boxSizing: 'border-box',
          overflowY: 'auto',
          background: '#fff',
        }}
      >
        <div style={{ width: '100%', maxWidth: 'clamp(400px, 33vw, 520px)', animation: 'aitg-materialize 0.6s ease-out 0.3s both' }}>
          {mode === 'forgot' ? (
            <form
              onSubmit={handleForgotSubmit}
              style={{
                padding: '8px 4px',
                display: 'flex',
                flexDirection: 'column',
                boxSizing: 'border-box',
              }}
            >
              <button
                type="button"
                onClick={handleBackToSignIn}
                style={{
                  alignSelf: 'flex-start',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 13.5,
                  fontWeight: 600,
                  color: 'var(--ink-secondary)',
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  margin: '0 0 20px',
                  cursor: 'pointer',
                }}
              >
                <FontAwesomeIcon icon={faArrowLeft} style={{ fontSize: 12 }} />
                Back to sign in
              </button>

              {resetSent ? (
                <>
                  <h2 style={{ fontSize: 28, fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--ink)', margin: '0 0 8px' }}>
                    Check your email
                  </h2>
                  <p style={{ fontSize: 15, color: 'var(--ink-muted)', margin: '0 0 32px' }}>
                    If an account exists for {email}, a reset link is on its way. The link expires in 1 hour.
                  </p>
                </>
              ) : (
                <>
                  <h2 style={{ fontSize: 28, fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--ink)', margin: '0 0 8px' }}>
                    Reset your password
                  </h2>
                  <p style={{ fontSize: 15, color: 'var(--ink-muted)', margin: '0 0 32px' }}>
                    Enter your email and we'll send you a link to reset it.
                  </p>

                  <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                      <label className="field">
                        <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Email</span>
                        <input
                          type="email"
                          required
                          autoFocus
                          autoComplete="username"
                          placeholder="Enter your email"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          style={{ padding: '15px 16px', fontSize: 15 }}
                        />
                      </label>

                      {error && (
                        <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
                          {error}
                        </div>
                      )}

                      <button
                        type="submit"
                        className="button-primary"
                        disabled={submitting}
                        style={{ padding: 16, fontSize: 15.5, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginTop: 4 }}
                      >
                        {submitting ? <LoadingDots label="Sending" /> : 'Send reset link'}
                      </button>
                    </div>
                  </fieldset>
                </>
              )}
            </form>
          ) : (
            <form
              onSubmit={handleSubmit}
              style={{
                padding: '8px 4px',
                display: 'flex',
                flexDirection: 'column',
                boxSizing: 'border-box',
              }}
            >
              <h2
                onClick={DEV_LOGIN_ENABLED ? handleDevAutofill : undefined}
                title={DEV_LOGIN_ENABLED ? 'Fill dev sign-in credentials' : undefined}
                style={{
                  fontSize: 28,
                  fontWeight: 700,
                  letterSpacing: '-0.01em',
                  color: 'var(--ink)',
                  margin: '0 0 8px',
                  cursor: DEV_LOGIN_ENABLED ? 'pointer' : undefined,
                }}
              >
                Welcome back
              </h2>
              <p style={{ fontSize: 15, color: 'var(--ink-muted)', margin: '0 0 24px' }}>Sign in to your Vantage account.</p>

              <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  <label className="field">
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Email</span>
                    <input
                      type="email"
                      required
                      autoComplete="username"
                      placeholder="Enter your email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      style={{ padding: '15px 16px', fontSize: 15 }}
                    />
                  </label>

                  <label className="field">
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Password</span>
                    <PasswordInput
                      required
                      autoComplete="current-password"
                      placeholder="Enter your password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      style={{ padding: '15px 16px', fontSize: 15 }}
                    />
                  </label>

                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      onClick={() => setMode('forgot')}
                      style={{
                        fontSize: 13.5,
                        color: 'var(--accent)',
                        background: 'none',
                        border: 'none',
                        padding: 0,
                        cursor: 'pointer',
                      }}
                    >
                      Forgot password?
                    </button>
                  </div>

                  {error && (
                    <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
                      {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    className="button-primary"
                    disabled={submitting}
                    style={{ padding: 16, fontSize: 15.5, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginTop: 4 }}
                  >
                    {submitting ? (
                      <LoadingDots label="Signing in" />
                    ) : (
                      <>
                        Sign in
                        <FontAwesomeIcon icon={faArrowRight} style={{ fontSize: 13 }} />
                      </>
                    )}
                  </button>
                </div>
              </fieldset>
            </form>
          )}
        </div>

        <div
          style={{
            // marginTop: 'auto' (not position: absolute) so this only gets pushed to
            // the section's bottom when there's spare room — on short viewports it
            // stays in normal flow right after the form instead of overlapping it.
            marginTop: 'auto',
            alignSelf: 'flex-end',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 4,
            paddingTop: 16,
            animation: 'aitg-materialize 0.6s ease-out 0.36s both',
          }}
        >
          <span className="decorative" style={{ fontSize: 13 }}>
            An initiative of
          </span>
          <OmnewaveBrand markSize={18} />
        </div>
      </section>
    </main>
  )
}
