import { useEffect, useState } from 'react'
import { ApiError, api, type UserRead } from '../api'
import { ForgotPassword } from './ForgotPassword'
import { LoadingDots } from './LoadingDots'
import { PasswordInput } from './PasswordInput'
import { VantageBrand } from './Brand'

const WIZARD_STEPS = [
  { label: 'Scan', desc: 'Every screen, mapped.', kind: 'scan' },
  { label: 'Discover', desc: 'Journeys that matter, found.', kind: 'discover' },
  { label: 'Generate', desc: 'Tests, written for you.', kind: 'generate' },
  { label: 'Run', desc: 'Coverage, in real time.', kind: 'run' },
] as const

const JOURNEY_ROWS = ['Customer Login & MFA', 'External Wire Transfer', 'Bill Pay Setup']
const GENERATE_COUNTS = ['5 tests', '7 tests', '5 tests']

function StepPreview({ kind }: { kind: (typeof WIZARD_STEPS)[number]['kind'] }) {
  if (kind === 'scan') {
    return (
      <div
        className="stat-tile-hover"
        style={{
          background: 'var(--canvas)',
          border: '1px solid rgba(15,23,42,0.08)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: '0 16px 32px -16px rgba(15,23,42,0.2)',
          padding: '8px 10px',
          boxSizing: 'border-box',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 0,
            height: 32,
            background: 'linear-gradient(180deg, var(--accent-wash) 0%, transparent 100%)',
            pointerEvents: 'none',
            animation: 'aitg-scan-sweep 1.2s ease-in-out both',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          <span style={{ width: 7, height: 7, borderRadius: 'var(--radius-full)', background: 'var(--border-strong)' }} />
          <span style={{ width: 7, height: 7, borderRadius: 'var(--radius-full)', background: 'var(--border-strong)' }} />
          <span style={{ width: 7, height: 7, borderRadius: 'var(--radius-full)', background: 'var(--border-strong)' }} />
          <span
            style={{
              flex: 1,
              background: 'var(--canvas-wash-alt)',
              borderRadius: 6,
              padding: '6px 12px',
              fontSize: 12,
              color: 'var(--ink-faint)',
              fontFamily: 'var(--font-mono)',
              marginLeft: 6,
            }}
          >
            app.northbridgebank.com
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          <span style={{ height: 9, width: '88%', background: 'var(--accent-wash)', borderRadius: 5, transformOrigin: 'left', animation: 'aitg-bar-grow 0.6s ease-out both' }} />
          <span style={{ height: 9, width: '64%', background: 'var(--accent-wash)', borderRadius: 5, transformOrigin: 'left', animation: 'aitg-bar-grow 0.6s ease-out 0.12s both' }} />
          <span style={{ height: 9, width: '78%', background: 'var(--accent-wash)', borderRadius: 5, transformOrigin: 'left', animation: 'aitg-bar-grow 0.6s ease-out 0.24s both' }} />
        </div>
      </div>
    )
  }

  if (kind === 'discover' || kind === 'generate') {
    return (
      <div
        className="stat-tile-hover"
        style={{
          background: 'var(--canvas)',
          border: '1px solid rgba(15,23,42,0.08)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: '0 16px 32px -16px rgba(15,23,42,0.2)',
          padding: '14px 16px',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        {JOURNEY_ROWS.map((name, i) => (
          <div
            key={name}
            className="stat-tile-hover"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '7px 14px',
              background: 'var(--canvas-wash)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              animation: `aitg-fade-up 0.4s ease-out ${i * 0.13}s both`,
            }}
          >
            <span
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: 'var(--ink)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {name}
            </span>
            {kind === 'discover' ? (
              <span
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--good-wash)',
                  color: 'var(--good)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 10,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                ✓
              </span>
            ) : (
              <span
                style={{
                  padding: '3px 9px',
                  borderRadius: 999,
                  fontSize: 10.5,
                  fontWeight: 600,
                  background: 'var(--accent-wash)',
                  color: 'var(--accent)',
                  flexShrink: 0,
                }}
              >
                {GENERATE_COUNTS[i]}
              </span>
            )}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div
      className="stat-tile-hover"
      style={{
        background: 'var(--canvas)',
        border: '1px solid rgba(15,23,42,0.08)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: '0 16px 32px -16px rgba(15,23,42,0.2)',
        padding: '7px 12px',
        boxSizing: 'border-box',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>Suite execution</span>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--good)' }}>94% coverage</span>
      </div>
      <div style={{ height: 6, background: 'var(--canvas-wash-alt)', borderRadius: 999, overflow: 'hidden', marginBottom: 8 }}>
        <div style={{ height: '100%', background: 'var(--good)', borderRadius: 999, animation: 'aitg-bar-fill 1.1s ease-out both' }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div className="stat-tile-hover" style={{ background: 'var(--canvas-wash)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '6px 10px' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>15</div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-muted)', marginTop: 2 }}>Journeys mapped</div>
        </div>
        <div className="stat-tile-hover" style={{ background: 'var(--canvas-wash)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '6px 10px' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>312</div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-muted)', marginTop: 2 }}>Tests generated</div>
        </div>
      </div>
    </div>
  )
}

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
  const [activeStep, setActiveStep] = useState(0)
  const [showForgotPassword, setShowForgotPassword] = useState(false)

  function handleDevAutofill() {
    if (!DEV_LOGIN_ENABLED) return
    setEmail(DEV_CREDENTIALS.email)
    setPassword(DEV_CREDENTIALS.password)
  }

  useEffect(() => {
    const timer = setInterval(() => setActiveStep((i) => (i + 1) % WIZARD_STEPS.length), 2600)
    return () => clearInterval(timer)
  }, [])

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

  if (showForgotPassword) {
    return <ForgotPassword onBackToSignIn={() => setShowForgotPassword(false)} />
  }

  return (
    <main
      style={{
        height: '100vh',
        display: 'flex',
        position: 'relative',
        overflow: 'hidden',
        boxSizing: 'border-box',
        background: '#fff',
      }}
    >
      <section
        style={{
          flex: '0 1 58%',
          minWidth: 0,
          height: '100%',
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'flex-start',
          padding: '24px 40px 18px 32px',
          boxSizing: 'border-box',
          background: 'linear-gradient(165deg, #FFFFFF 0%, #F4F6FA 45%, #ECEFF5 100%)',
        }}
      >
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: 'radial-gradient(rgba(15,23,42,0.05) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
            pointerEvents: 'none',
          }}
        />
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: '6%',
            left: '50%',
            marginLeft: -410,
            width: 820,
            height: 820,
            borderRadius: 'var(--radius-full)',
            background: 'radial-gradient(circle, var(--accent-wash) 0%, transparent 70%)',
            pointerEvents: 'none',
            animation: 'aitg-drift 16s ease-in-out infinite',
          }}
        />

        <div
          onClick={DEV_LOGIN_ENABLED ? handleDevAutofill : undefined}
          title={DEV_LOGIN_ENABLED ? 'Fill dev sign-in credentials' : undefined}
          style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginBottom: 18,
            flexShrink: 0,
            cursor: DEV_LOGIN_ENABLED ? 'pointer' : undefined,
            animation: 'aitg-materialize 0.6s ease-out both',
          }}
        >
          <VantageBrand markSize={24} />
        </div>

        <h1
          style={{
            position: 'relative',
            fontSize: 28,
            fontWeight: 600,
            lineHeight: 1.25,
            letterSpacing: '-0.01em',
            color: 'var(--ink-secondary)',
            maxWidth: 'clamp(640px, 60vw, 1040px)',
            margin: '0 0 8px',
            animation: 'aitg-materialize 0.6s ease-out 0.08s both',
          }}
        >
          Point it at your app.
          <br />
          <span style={{ color: 'var(--accent)' }}>Get a production-ready test suite back.</span>
        </h1>
        <div
          style={{
            position: 'relative',
            fontSize: 11.5,
            fontWeight: 700,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--ink-secondary)',
            margin: '14px 0 6px',
            animation: 'aitg-materialize 0.6s ease-out 0.18s both',
          }}
        >
          How it works
        </div>

        <div
          style={{
            maxWidth: '100%',
            paddingRight: 8,
            animation: 'aitg-materialize 0.7s ease-out 0.22s both',
          }}
        >
          {WIZARD_STEPS.map((step, i) => {
            const completed = i < activeStep
            const active = i === activeStep
            const isLast = i === WIZARD_STEPS.length - 1
            return (
              <div key={step.label} onClick={() => setActiveStep(i)} style={{ display: 'flex', cursor: 'pointer' }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 26, flexShrink: 0, marginRight: 14 }}>
                  <div
                    style={{
                      width: 26,
                      height: 26,
                      flexShrink: 0,
                      borderRadius: 'var(--radius-full)',
                      background: completed
                        ? 'linear-gradient(var(--good-wash), var(--good-wash)), var(--canvas)'
                        : active
                          ? 'linear-gradient(var(--accent-wash), var(--accent-wash)), var(--canvas)'
                          : 'var(--canvas-wash-alt)',
                      color: completed ? 'var(--good)' : active ? 'var(--accent)' : 'var(--ink-secondary)',
                      border: `1.5px solid ${completed ? 'var(--good)' : active ? 'var(--accent)' : 'var(--border-strong)'}`,
                      boxShadow: active ? '0 0 0 4px var(--accent-wash)' : 'none',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 12,
                      fontWeight: 700,
                      transition: 'background-color 0.25s ease, color 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease',
                    }}
                  >
                    {completed ? <span style={{ animation: 'aitg-check-pop 0.3s ease-out both' }}>✓</span> : i + 1}
                  </div>
                  {!isLast && (
                    <div
                      style={{
                        flex: 1,
                        width: 1.5,
                        marginTop: 2,
                        background:
                          'linear-gradient(180deg, transparent, var(--accent) 45%, transparent 90%), var(--border)',
                        backgroundSize: '100% 200%, 100% 100%',
                        animation: 'aitg-line-flow 3s linear infinite',
                      }}
                    />
                  )}
                </div>
                <div style={{ flex: 1, paddingBottom: 8 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 4 }}>{step.label}</div>
                  <div style={{ fontSize: 13.5, color: 'var(--ink-muted)', marginBottom: active ? 5 : 0 }}>{step.desc}</div>

                  {active && (
                    <div style={{ height: 166, overflow: 'hidden', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                      <StepPreview kind={step.kind} />
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      <section
        style={{
          flex: '0 1 42%',
          minWidth: 0,
          height: '100%',
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '40px 56px',
          boxSizing: 'border-box',
          overflowY: 'auto',
          background: '#fff',
        }}
      >
        <div style={{ width: '100%', maxWidth: 'clamp(400px, 33vw, 520px)', animation: 'aitg-materialize 0.6s ease-out 0.3s both' }}>
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
                fontSize: 20,
                fontWeight: 700,
                color: 'var(--ink)',
                margin: '0 0 4px',
                cursor: DEV_LOGIN_ENABLED ? 'pointer' : undefined,
              }}
            >
              Sign in
            </h2>
            <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 24px' }}>Use your work account to continue</p>

            <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <label className="field">
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                    Work email <span style={{ color: 'var(--danger)' }}>*</span>
                  </span>
                  <input
                    type="email"
                    required
                    autoComplete="username"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    style={{ padding: '11px 14px', fontSize: 14.5 }}
                  />
                </label>

                <label className="field">
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                    Password <span style={{ color: 'var(--danger)' }}>*</span>
                  </span>
                  <PasswordInput
                    required
                    autoComplete="current-password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    style={{ padding: '11px 14px', fontSize: 14.5 }}
                  />
                </label>

                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    onClick={() => setShowForgotPassword(true)}
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

                <button type="submit" className="button-primary" disabled={submitting} style={{ padding: 12, fontSize: 14.5 }}>
                  {submitting ? <LoadingDots label="Signing in" /> : 'Sign in'}
                </button>
              </div>
            </fieldset>

            <p
              className="decorative"
              style={{ textAlign: 'center', fontSize: 12, margin: '20px 0 0', animation: 'aitg-materialize 0.6s ease-out 0.36s both' }}
            >
              © 2026 Vantage. All Rights Reserved
            </p>
          </form>
        </div>
      </section>
    </main>
  )
}
