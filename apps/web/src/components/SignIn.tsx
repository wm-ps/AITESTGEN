import { useEffect, useState } from 'react'
import { ApiError, api, type UserRead } from '../api'
import { Logo } from './Logo'

const WIZARD_STEPS = [
  { label: 'Scan', desc: 'Reads every screen in your app.', kind: 'scan' },
  { label: 'Discover', desc: 'Finds the critical user journeys.', kind: 'discover' },
  { label: 'Generate', desc: 'Turns journeys into test scenarios.', kind: 'generate' },
  { label: 'Run', desc: 'Executes the suite and tracks coverage.', kind: 'run' },
] as const

const JOURNEY_ROWS = ['Customer Login & MFA', 'External Wire Transfer', 'Bill Pay Setup']
const GENERATE_COUNTS = ['5 tests', '7 tests', '5 tests']

function StepPreview({ kind }: { kind: (typeof WIZARD_STEPS)[number]['kind'] }) {
  if (kind === 'scan') {
    return (
      <div
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
        style={{
          background: 'var(--canvas)',
          border: '1px solid rgba(15,23,42,0.08)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: '0 16px 32px -16px rgba(15,23,42,0.2)',
          padding: '12px 14px',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        {JOURNEY_ROWS.map((name, i) => (
          <div
            key={name}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '7px 12px',
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
        <div style={{ background: 'var(--canvas-wash)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '6px 10px' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>15</div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-muted)', marginTop: 2 }}>Journeys mapped</div>
        </div>
        <div style={{ background: 'var(--canvas-wash)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '6px 10px' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>312</div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-muted)', marginTop: 2 }}>Tests generated</div>
        </div>
      </div>
    </div>
  )
}

export function SignIn({ onSignedIn }: { onSignedIn: (user: UserRead) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [activeStep, setActiveStep] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setActiveStep((i) => (i + 1) % WIZARD_STEPS.length), 2600)
    return () => clearInterval(timer)
  }, [activeStep])

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

  return (
    <main
      style={{
        height: '100vh',
        display: 'flex',
        position: 'relative',
        overflow: 'hidden',
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
          opacity: 0.55,
          pointerEvents: 'none',
          animation: 'aitg-drift 14s ease-in-out infinite',
        }}
      />
      <div aria-hidden="true" style={{ position: 'absolute', top: '6%', left: '50%', width: 0, height: 0, pointerEvents: 'none' }}>
        {[0, 1.5, 3].map((delay) => (
          <div
            key={delay}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: 340,
              height: 340,
              margin: '-170px 0 0 -170px',
              borderRadius: 'var(--radius-full)',
              border: '1px solid var(--accent)',
              opacity: 0,
              animation: `aitg-radar-ring 4.5s ease-out infinite`,
              animationDelay: `${delay}s`,
            }}
          />
        ))}
      </div>

      <section
        style={{
          flex: '0 1 52%',
          minWidth: 0,
          height: '100%',
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'flex-start',
          padding: '24px 12px 18px 40px',
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginBottom: 6,
            flexShrink: 0,
            animation: 'aitg-materialize 0.6s ease-out both',
          }}
        >
          <Logo size={30} />
          <span style={{ fontWeight: 800, fontSize: 22, color: 'var(--ink)', letterSpacing: '-0.02em' }}>AITestGen</span>
        </div>

        <h1
          style={{
            position: 'relative',
            fontSize: 28,
            fontWeight: 600,
            lineHeight: 1.25,
            letterSpacing: '-0.01em',
            color: 'var(--ink-secondary)',
            maxWidth: 'clamp(620px, 50vw, 900px)',
            margin: '0 0 8px',
            animation: 'aitg-materialize 0.6s ease-out 0.08s both',
          }}
        >
          Point it at your app. <span style={{ color: 'var(--accent)' }}>Get a full test suite back.</span>
        </h1>
        <p
          style={{
            position: 'relative',
            fontSize: 16.5,
            color: 'var(--ink-muted)',
            maxWidth: 'clamp(540px, 44vw, 780px)',
            lineHeight: 1.45,
            margin: '0 0 10px',
            animation: 'aitg-materialize 0.6s ease-out 0.14s both',
          }}
        >
          Scans your product, discovers every user journey, and writes working tests for it.
        </p>
        <div
          style={{
            position: 'relative',
            fontSize: 11.5,
            fontWeight: 700,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--ink-secondary)',
            marginBottom: 6,
            animation: 'aitg-materialize 0.6s ease-out 0.18s both',
          }}
        >
          How it works
        </div>

        <div
          style={{
            position: 'relative',
            maxWidth: 'clamp(660px, 52vw, 940px)',
            paddingLeft: 32,
            animation: 'aitg-materialize 0.7s ease-out 0.22s both',
          }}
        >
          <div style={{ position: 'absolute', left: 11, top: 8, bottom: 16, width: 1.5, background: 'var(--border)' }} />

          {WIZARD_STEPS.map((step, i) => {
            const completed = i < activeStep
            const active = i === activeStep
            return (
              <div
                key={step.label}
                onClick={() => setActiveStep(i)}
                style={{ position: 'relative', marginBottom: 8, cursor: 'pointer' }}
              >
                <div
                  style={{
                    position: 'absolute',
                    left: -32,
                    top: 0,
                    width: 26,
                    height: 26,
                    borderRadius: 'var(--radius-full)',
                    background: completed ? 'var(--good-wash)' : active ? 'var(--accent-wash)' : 'var(--canvas-wash-alt)',
                    color: completed ? 'var(--good)' : active ? 'var(--accent)' : 'var(--ink-muted)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 12,
                    fontWeight: 700,
                    transition: 'background-color 0.25s ease, color 0.25s ease',
                  }}
                >
                  {completed ? <span style={{ animation: 'aitg-check-pop 0.3s ease-out both' }}>✓</span> : i + 1}
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 4 }}>{step.label}</div>
                <div style={{ fontSize: 13.5, color: 'var(--ink-muted)', marginBottom: active ? 5 : 0 }}>{step.desc}</div>

                {active && (
                  <div style={{ height: 132, overflow: 'hidden', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <StepPreview kind={step.kind} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      <section
        style={{
          flex: '0 1 48%',
          minWidth: 0,
          height: '100%',
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'flex-start',
          padding: '60px 40px 20px 20px',
          boxSizing: 'border-box',
          overflowY: 'auto',
        }}
      >
        <div style={{ width: '100%', maxWidth: 'clamp(400px, 33vw, 520px)', animation: 'aitg-materialize 0.6s ease-out 0.3s both' }}>
          <form
            onSubmit={handleSubmit}
            className="card-panel"
            style={{
              padding: '24px 34px',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box',
              overflow: 'hidden',
              boxShadow: '0 8px 20px -12px rgba(15,23,42,0.14)',
            }}
          >
            <div style={{ height: 3, background: 'linear-gradient(90deg, var(--accent) 0%, var(--accent-wash) 100%)', margin: '-24px -34px 18px' }} />
            <h2 style={{ fontSize: 19, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>Sign in</h2>
            <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 22px' }}>Use your work account to continue</p>

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
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{ padding: '11px 14px', fontSize: 14.5 }}
                />
              </label>

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <a href="#" style={{ fontSize: 13.5, color: 'var(--accent)', textDecoration: 'none' }}>
                  Forgot password?
                </a>
              </div>

              {error && (
                <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
                  {error}
                </div>
              )}

              <button type="submit" className="button-primary" disabled={submitting} style={{ padding: 12, fontSize: 14.5 }}>
                {submitting ? 'Signing in…' : 'Sign in'}
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0' }} aria-hidden="true">
              <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              <span style={{ fontSize: 12.5, color: 'var(--ink-faint)' }}>OR</span>
              <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            </div>

            <button type="button" className="button-secondary" style={{ padding: 12, fontSize: 14.5 }}>
              Continue with Single Sign-On
            </button>

            <p
              className="decorative"
              style={{ textAlign: 'center', fontSize: 12, margin: '20px 0 0', animation: 'aitg-materialize 0.6s ease-out 0.36s both' }}
            >
              © 2026 AITestGen, Inc. <a href="#" className="decorative">Terms</a> · <a href="#" className="decorative">Privacy</a> ·{' '}
              <a href="#" className="decorative">Support</a>
            </p>
          </form>
        </div>
      </section>
    </main>
  )
}
