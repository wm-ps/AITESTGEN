import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCircleDot, faCode, faWandMagicSparkles } from '@fortawesome/free-solid-svg-icons'
import { faBell } from '@fortawesome/free-regular-svg-icons'
import { faIcon } from '../faIcon'

const CircleDot = faIcon(faCircleDot)
const Code2 = faIcon(faCode)
const Sparkles = faIcon(faWandMagicSparkles)

// Vantage V2's "Record and play" tab — capture a flow by hand in the real
// browser, replay it as an ordinary Playwright spec. No backend for this
// yet (distinct from LiveExplorationPanel's AI-driven exploration-from-a-
// prompt flow) — shown as an early-access pitch per the prototype's own
// framing, not wired to anything real.
const PITCH = [
  { icon: CircleDot, title: 'Capture once, in the real browser', body: 'Click through the flow you care about. Vantage records intent, not brittle coordinates.' },
  { icon: Code2, title: 'Replays as ordinary Playwright', body: 'The session becomes a readable spec using the same page objects as the generated suite.' },
  { icon: Sparkles, title: 'Maintained like everything else', body: 'Recorded tests inherit self-healing locators, test data and CI scheduling.' },
]

export function RecordAndPlay() {
  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Record and play</h1>
          <span style={{ fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 6, background: 'rgba(30,150,138,0.14)', color: 'var(--accent-2)', border: '1px solid rgba(30,150,138,0.28)' }}>
            Coming soon
          </span>
        </div>
        <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4, maxWidth: 620 }}>
          Walk through a flow in the browser once. Vantage turns the session into a maintained Playwright test that
          lives alongside the generated suite — same locators, same fixtures, same self-healing.
        </div>
        <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>Early access opens next quarter.</div>
      </div>

      <div
        style={{
          background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
          backdropFilter: 'blur(16px) saturate(1.25)',
          border: '1px solid var(--border-1)',
          borderRadius: 14,
          padding: 24,
          boxShadow: 'var(--panel-shadow)',
          display: 'flex',
          flexDirection: 'column',
          gap: 18,
        }}
      >
        {PITCH.map((p) => {
          const Icon = p.icon
          return (
            <div key={p.title} style={{ display: 'flex', alignItems: 'flex-start', gap: 13 }}>
              <div style={{ width: 32, height: 32, flex: 'none', borderRadius: 8, background: 'var(--chip)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-2)' }}>
                <Icon size={14} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>{p.title}</div>
                <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 3 }}>{p.body}</div>
              </div>
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button
          type="button"
          disabled
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 38, padding: '0 20px', borderRadius: 8, background: 'var(--accent)', color: '#fff', fontSize: 13.5, fontWeight: 600, border: 'none', cursor: 'not-allowed', opacity: 0.6, boxShadow: 'var(--accent-glow)' }}
        >
          Request early access
        </button>
        <button
          type="button"
          disabled
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 38, padding: '0 18px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--fg-2)', fontSize: 13.5, fontWeight: 500, cursor: 'not-allowed', opacity: 0.6 }}
        >
          See how it works
        </button>
      </div>

      <div
        style={{
          background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
          backdropFilter: 'blur(16px) saturate(1.25)',
          border: '1px solid var(--border-1)',
          borderRadius: 14,
          boxShadow: 'var(--panel-shadow)',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 20px', borderBottom: '1px solid var(--border-2)' }}>
          <CircleDot size={12} color="var(--fg-4)" />
          <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)', flex: 1 }}>Your recordings</div>
          <span style={{ fontSize: 11.5, color: 'var(--fg-4)' }}>Reserved for this workspace</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '52px 24px 56px' }}>
          <RecordingsIllustration />
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.01em' }}>Recordings will appear here</div>
          <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 7, maxWidth: 400, textAlign: 'center', lineHeight: '20px' }}>
            Once early access is enabled, every captured session lands in this list with its replay, generated spec and
            screenshots.
          </div>
          <button
            type="button"
            disabled
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 36, padding: '0 18px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--fg-2)', fontSize: 13, fontWeight: 600, cursor: 'not-allowed', opacity: 0.6, marginTop: 22 }}
          >
            <FontAwesomeIcon icon={faBell} style={{ fontSize: 11 }} />
            Notify me when it ships
          </button>
        </div>
      </div>
    </div>
  )
}

// Matches the prototype's own illustration exactly: a scrubber bar with a
// playhead partway through, two overlapping video-frame cards behind it,
// and a recording-dot badge — the one illustration this screen doesn't
// share with EmptyState.tsx's family, since nothing else in the app is a
// video/session recording.
function RecordingsIllustration() {
  return (
    <div style={{ position: 'relative', width: 196, height: 120, marginBottom: 24 }}>
      <div style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', width: 220, height: 220, borderRadius: 1000, background: 'var(--glow)' }} />
      <div style={{ position: 'absolute', left: 16, top: 8, width: 74, height: 52, borderRadius: 9, background: 'var(--panel-2)', border: '1px solid var(--border-2)' }} />
      <div style={{ position: 'absolute', left: 60, top: 22, width: 74, height: 52, borderRadius: 9, background: 'var(--panel-2)', border: '1px solid var(--border-3)', boxShadow: '0 12px 26px rgba(0,0,0,0.22)' }} />
      <div style={{ position: 'absolute', right: 8, top: 0, width: 46, height: 46, borderRadius: 1000, background: 'rgba(245,86,107,0.12)', border: '1px solid rgba(245,86,107,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ width: 13, height: 13, borderRadius: 1000, background: 'var(--bad)' }} />
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 26, height: 8, borderRadius: 1000, background: 'var(--panel-2)', border: '1px solid var(--border-2)', overflow: 'hidden', display: 'flex' }}>
        <div style={{ width: '34%', height: '100%', background: 'var(--accent)', opacity: 0.55 }} />
      </div>
      <div style={{ position: 'absolute', left: 'calc(34% - 7px)', bottom: 19, width: 14, height: 22, borderRadius: 4, background: 'var(--accent)', boxShadow: '0 4px 14px rgba(30,150,138,0.4)' }} />
    </div>
  )
}
