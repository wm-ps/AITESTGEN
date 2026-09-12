import { AppIdentityLine } from './AppIdentityLine'

// Vantage V2's "Record and play" tab — capture a flow by hand in the real
// browser, replay it as an ordinary Playwright spec. No backend for this yet
// (distinct from LiveExplorationPanel's AI-driven exploration-from-a-prompt
// flow) — an early-access placeholder (title/subheader/context/illustration
// only, no pitch copy or dead buttons) until it's actually wired up.
export function RecordAndPlay({ applicationName, applicationUrl }: { applicationName: string; applicationUrl: string }) {
  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Record and play</h1>
          <span style={{ fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 6, background: 'rgba(30,150,138,0.14)', color: 'var(--accent-2)', border: '1px solid rgba(30,150,138,0.28)' }}>
            Coming soon
          </span>
        </div>
        <AppIdentityLine name={applicationName} url={applicationUrl} />
        <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4, maxWidth: 620 }}>
          Walk through a flow in the browser once. Vantage turns the session into a maintained Playwright test that
          lives alongside the generated suite — same locators, same fixtures, same self-healing.
        </div>
      </div>

      <div
        style={{
          background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
          backdropFilter: 'blur(16px) saturate(1.25)',
          border: '1px solid var(--border-1)',
          borderRadius: 14,
          boxShadow: 'var(--panel-shadow)',
          display: 'flex',
          justifyContent: 'center',
          padding: '56px 24px',
        }}
      >
        <RecordingsIllustration />
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
