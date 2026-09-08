import { useState } from 'react'

function PlayIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M6 4.5v15l13-7.5z" />
    </svg>
  )
}

// Run Suite Flow: "Run Suite" now opens a popover (Full Suite / Run
// Journey(s)…) instead of triggering a full-scope run directly — same
// button-anchored-menu shape DiscoverJourneys.tsx's JourneyRowMenu already
// uses (local `open` state, fixed click-outside overlay + absolute menu).
export function RunSuiteButton({
  running,
  onFullSuite,
  onOpenJourneysDialog,
}: {
  running: boolean
  onFullSuite: () => void
  onOpenJourneysDialog: () => void
}) {
  const [open, setOpen] = useState(false)

  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        className="button-primary"
        disabled={running}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
      >
        <PlayIcon />
        {running ? 'Running…' : 'Run Suite'}
      </button>
      {open && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 49 }} onClick={() => setOpen(false)} />
          <div
            role="menu"
            className="card-panel"
            style={{
              position: 'absolute',
              right: 0,
              top: 'calc(100% + 6px)',
              minWidth: 200,
              boxShadow: '0 12px 28px rgba(15,23,42,0.14)',
              overflow: 'hidden',
              zIndex: 50,
            }}
          >
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                onFullSuite()
              }}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                background: 'none',
                border: 'none',
                fontSize: 13.5,
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              Full Suite
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                onOpenJourneysDialog()
              }}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                background: 'none',
                border: 'none',
                fontSize: 13.5,
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              Run Journey(s)…
            </button>
          </div>
        </>
      )}
    </div>
  )
}
