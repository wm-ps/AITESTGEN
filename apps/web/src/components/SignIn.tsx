import { useState } from 'react'
import { ApiError, api, type UserRead } from '../api'
import { Logo } from './Logo'

export function SignIn({ onSignedIn }: { onSignedIn: (user: UserRead) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

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
        minHeight: '100svh',
        display: 'flex',
        position: 'relative',
        overflow: 'hidden',
        background: 'linear-gradient(165deg, var(--paper) 0%, var(--surface) 45%, var(--surface-hover) 100%)',
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
          top: '4%',
          left: '32%',
          width: 900,
          height: 900,
          borderRadius: 'var(--radius-full)',
          background: 'radial-gradient(circle, var(--signal-wash) 0%, transparent 65%)',
          pointerEvents: 'none',
          animation: 'aitg-drift 14s ease-in-out infinite',
        }}
      />

      <section
        style={{
          flex: 1.2,
          minWidth: 0,
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '40px 64px',
        }}
      >
        <div
          style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-3)',
            marginBottom: 'var(--space-8)',
            animation: 'aitg-materialize 0.6s ease-out both',
          }}
        >
          <Logo size={34} />
          <span style={{ fontWeight: 650, fontSize: 15 }}>AITestGen</span>
        </div>

        <h1
          style={{
            position: 'relative',
            fontSize: 38,
            lineHeight: 1.15,
            letterSpacing: '-0.02em',
            margin: '0 0 12px',
            maxWidth: 560,
            animation: 'aitg-materialize 0.6s ease-out 0.08s both',
          }}
        >
          Enterprise Test Generation,
          <br />
          <span style={{ color: 'var(--signal)' }}>Simplified.</span>
        </h1>
        <p
          style={{
            position: 'relative',
            fontSize: 15,
            fontStyle: 'italic',
            color: 'var(--ink-muted)',
            whiteSpace: 'nowrap',
            margin: 0,
            animation: 'aitg-materialize 0.6s ease-out 0.14s both',
          }}
        >
          Comprehensive test coverage from application behavior.
        </p>

        <div
          style={{
            position: 'relative',
            marginTop: 36,
            maxWidth: 440,
            animation: 'aitg-materialize 0.7s ease-out 0.22s both',
          }}
          aria-hidden="true"
        >
          <div
            className="card-panel"
            style={{
              position: 'relative',
              overflow: 'hidden',
              boxShadow: '0 28px 54px -18px rgba(15,23,42,0.28)',
              animation: 'aitg-drift 9s ease-in-out infinite',
            }}
          >
            <div
              style={{
                height: 28,
                background: 'var(--surface)',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                padding: '0 12px',
              }}
            >
              <span style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: 'var(--border-strong)' }} />
              <span style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: 'var(--border-strong)' }} />
              <span style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: 'var(--border-strong)' }} />
              <span
                style={{
                  marginLeft: 8,
                  padding: '2px 8px',
                  borderRadius: 4,
                  background: 'var(--surface-hover)',
                  fontSize: 9,
                  color: 'var(--ink-faint)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                app.aitestgen.io
              </span>
            </div>

            <div
              style={{
                height: 32,
                background: 'var(--paper)',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 14px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 14, height: 14, borderRadius: 4, background: 'var(--signal)' }} />
                <span style={{ fontSize: 9, fontWeight: 700 }}>AITestGen</span>
              </div>
              <span
                style={{
                  width: 16,
                  height: 16,
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 7,
                  fontWeight: 700,
                  color: 'var(--ink-muted)',
                }}
              >
                SC
              </span>
            </div>

            <div style={{ position: 'relative', height: 132 }}>
              <div
                style={{
                  position: 'absolute',
                  inset: 10,
                  display: 'flex',
                  gap: 7,
                  animation: 'aitg-crossfade-a 9s ease-in-out infinite',
                }}
              >
                <div style={{ flex: '0 0 44%', background: 'var(--paper)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
                  <div style={{ padding: '7px 9px', background: 'var(--signal-wash)', borderLeft: '2px solid var(--signal)' }}>
                    <div style={{ fontSize: 8, fontWeight: 650 }}>Customer Login &amp; MFA</div>
                    <span style={{ display: 'inline-block', marginTop: 4, padding: '1px 5px', borderRadius: 999, fontSize: 6.5, fontWeight: 650, background: 'var(--good-wash)', color: 'var(--good)' }}>
                      Approved
                    </span>
                  </div>
                  <div style={{ padding: '7px 9px', borderTop: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 8, fontWeight: 650 }}>External Wire Transfer</div>
                    <span style={{ display: 'inline-block', marginTop: 4, padding: '1px 5px', borderRadius: 999, fontSize: 6.5, fontWeight: 650, background: 'var(--warn-wash)', color: 'var(--warn)' }}>
                      Needs Review
                    </span>
                  </div>
                  <div style={{ padding: '7px 9px', borderTop: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 8, fontWeight: 650 }}>Bill Pay Setup</div>
                    <span style={{ display: 'inline-block', marginTop: 4, padding: '1px 5px', borderRadius: 999, fontSize: 6.5, fontWeight: 650, background: 'var(--good-wash)', color: 'var(--good)' }}>
                      Approved
                    </span>
                  </div>
                </div>
                <div style={{ flex: 1, minWidth: 0, background: 'var(--paper)', border: '1px solid var(--border)', borderRadius: 8, padding: 9 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, marginBottom: 2 }}>Customer Login &amp; MFA</div>
                  <div style={{ fontSize: 7, color: 'var(--ink-muted)', marginBottom: 8, lineHeight: 1.4 }}>
                    Authenticate returning customers via SMS one-time passcode.
                  </div>
                  <div style={{ display: 'flex', gap: 4, marginBottom: 9 }}>
                    <span style={{ padding: '3px 7px', borderRadius: 5, fontSize: 7, fontWeight: 650, background: 'var(--good)', color: '#fff' }}>✓ Approve</span>
                    <span style={{ padding: '3px 7px', borderRadius: 5, fontSize: 7, fontWeight: 650, background: 'var(--paper)', border: '1px solid var(--border)', color: 'var(--ink-muted)' }}>
                      Flag
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ width: 10, height: 10, borderRadius: 'var(--radius-full)', background: 'var(--signal-wash)', color: 'var(--signal)', fontSize: 6, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        1
                      </span>
                      <span style={{ fontSize: 7, color: 'var(--ink)' }}>Submit credentials</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ width: 10, height: 10, borderRadius: 'var(--radius-full)', background: 'var(--signal-wash)', color: 'var(--signal)', fontSize: 6, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        2
                      </span>
                      <span style={{ fontSize: 7, color: 'var(--ink)' }}>Verify MFA code</span>
                    </div>
                  </div>
                </div>
                <div
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '55%',
                    height: '100%',
                    background: 'linear-gradient(100deg, transparent 0%, rgba(255,255,255,0.7) 50%, transparent 100%)',
                    pointerEvents: 'none',
                    animation: 'aitg-shimmer-sweep 5s ease-in-out infinite',
                  }}
                />
              </div>

              <div style={{ position: 'absolute', inset: 10, animation: 'aitg-crossfade-b 9s ease-in-out infinite' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 7 }}>
                  <span style={{ fontSize: 8, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Executive Summary</span>
                  <span style={{ fontSize: 6.5, color: 'var(--ink-faint)' }}>Last 30 days</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5, marginBottom: 7 }}>
                  <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
                    <div style={{ fontSize: 12, fontWeight: 700 }}>94%</div>
                    <div style={{ fontSize: 6.5, color: 'var(--ink-muted)', marginTop: 1 }}>Test coverage</div>
                  </div>
                  <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
                    <div style={{ fontSize: 12, fontWeight: 700 }}>15</div>
                    <div style={{ fontSize: 6.5, color: 'var(--ink-muted)', marginTop: 1 }}>Journeys mapped</div>
                  </div>
                  <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
                    <div style={{ fontSize: 12, fontWeight: 700 }}>312</div>
                    <div style={{ fontSize: 6.5, color: 'var(--ink-muted)', marginTop: 1 }}>Tests generated</div>
                  </div>
                  <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
                    <div style={{ fontSize: 12, fontWeight: 700 }}>3.2m</div>
                    <div style={{ fontSize: 6.5, color: 'var(--ink-muted)', marginTop: 1 }}>Avg. suite time</div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 26 }}>
                  <span style={{ flex: 1, background: 'var(--signal-wash)', borderRadius: '2px 2px 0 0', height: '35%' }} />
                  <span style={{ flex: 1, background: 'var(--signal-wash)', borderRadius: '2px 2px 0 0', height: '48%' }} />
                  <span style={{ flex: 1, background: 'var(--signal-wash)', borderRadius: '2px 2px 0 0', height: '42%' }} />
                  <span style={{ flex: 1, background: 'var(--signal-wash)', borderRadius: '2px 2px 0 0', height: '60%' }} />
                  <span style={{ flex: 1, background: 'var(--signal-wash)', borderRadius: '2px 2px 0 0', height: '70%' }} />
                  <span style={{ flex: 1, background: 'var(--signal)', borderRadius: '2px 2px 0 0', height: '85%' }} />
                  <span style={{ flex: 1, background: 'var(--signal)', borderRadius: '2px 2px 0 0', height: '100%' }} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section
        style={{
          flex: 1,
          minWidth: 0,
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 'var(--space-6)',
        }}
      >
        <div style={{ width: '100%', maxWidth: 380, animation: 'aitg-materialize 0.6s ease-out 0.3s both' }}>
          <form
            onSubmit={handleSubmit}
            className="card-panel"
            style={{
              padding: 'var(--space-8)',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box',
              overflow: 'hidden',
              boxShadow: '0 20px 40px -16px rgba(15,23,42,0.12), 0 1px 2px rgba(15,23,42,0.04)',
            }}
          >
            <div style={{ height: 3, background: 'linear-gradient(90deg, var(--signal) 0%, var(--signal-wash) 100%)', margin: '-32px -32px 24px' }} />
            <h2 style={{ fontSize: 18, fontWeight: 650, margin: '0 0 4px' }}>Sign in</h2>
            <p className="caption" style={{ margin: '0 0 24px', fontSize: 13 }}>
              Use your work account to continue
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              <label className="field">
                <span className="label">Work email</span>
                <input
                  type="email"
                  required
                  autoComplete="username"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>

              <label className="field">
                <span className="label">Password</span>
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>

              {error && (
                <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
                  {error}
                </div>
              )}

              <button type="submit" className="button-primary" disabled={submitting} style={{ padding: 11 }}>
                {submitting ? 'Signing in…' : 'Sign in'}
              </button>
            </div>

            <p
              className="caption"
              style={{ textAlign: 'center', fontSize: 12, margin: '20px 0 0', animation: 'aitg-materialize 0.6s ease-out 0.36s both' }}
            >
              Data encrypted in transit and at rest
            </p>
          </form>
        </div>
      </section>
    </main>
  )
}
