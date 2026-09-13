import { faCircleNotch } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { VantageBrand } from './Brand'

// The very first render, before `api.me()` resolves — used to just return
// `null` (a blank white flash) since there's no signed-in chrome to show a
// GlobalLoadingOverlay inside yet.
export function AppBootLoader() {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg)',
      }}
    >
      <VantageBrand markSize={30} />
    </div>
  )
}

// Brief cross-screen transitions (logout, resume-application, generate
// suite) used to set App.tsx's `globalLoading` message but nothing ever
// rendered it — the screen just froze with no feedback, which is exactly
// the "looks hung" complaint that state was introduced to fix. Same
// expanding-ring vocabulary GenerationLoader.tsx uses (v2-ring), scaled down
// for a transition that's over in a second or two rather than a multi-minute
// wait, instead of a generic spinner.
export function GlobalLoadingOverlay({ message }: { message: string }) {
  return (
    <div
      role="status"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 200,
        background: 'rgba(15,23,42,0.28)',
        backdropFilter: 'blur(2px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          padding: '18px 26px',
          borderRadius: 14,
          background: 'linear-gradient(180deg,rgba(255,255,255,0.96),rgba(255,255,255,0.86))',
          backdropFilter: 'blur(20px) saturate(1.3)',
          border: '1px solid var(--border-1)',
          boxShadow: '0 30px 70px rgba(8,12,20,0.28), var(--panel-shadow)',
        }}
      >
        <div style={{ position: 'relative', width: 34, height: 34, flex: 'none' }}>
          <div style={{ position: 'absolute', inset: 0, borderRadius: 1000, border: '1px solid var(--accent-2)', animation: 'v2-ring 1.6s ease-out infinite' }} />
          <div style={{ position: 'absolute', inset: 0, borderRadius: 1000, border: '1px solid var(--accent-2)', animation: 'v2-ring 1.6s ease-out 0.8s infinite' }} />
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: 1000,
              background: 'var(--panel-hi)',
              border: '1px solid var(--border-2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--accent-2)',
            }}
          >
            <FontAwesomeIcon icon={faCircleNotch} style={{ fontSize: 13, animation: 'aitg-spin 0.8s linear infinite' }} />
          </div>
        </div>
        <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>{message}…</span>
      </div>
    </div>
  )
}
