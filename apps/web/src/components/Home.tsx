import { useEffect, useState } from 'react'
import { api, type ApplicationRead, type UserRead } from '../api'

function FolderIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3.5 7.2A1.7 1.7 0 0 1 5.2 5.5h3.4l1.7 1.7h8a1.7 1.7 0 0 1 1.7 1.7v8.4a1.7 1.7 0 0 1-1.7 1.7H5.2a1.7 1.7 0 0 1-1.7-1.7V7.2Z" />
    </svg>
  )
}

function ApplicationCard({
  application,
  onResume,
}: {
  application: ApplicationRead
  onResume: () => void
}) {
  const [journeyCount, setJourneyCount] = useState<number | null>(null)
  const [scenarioCount, setScenarioCount] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.listJourneys(application.id), api.listScenarios(application.id)]).then(
      ([journeys, scenarios]) => {
        if (cancelled) return
        setJourneyCount(journeys.length)
        setScenarioCount(scenarios.length)
      },
    )
    return () => {
      cancelled = true
    }
  }, [application.id])

  // ponytail: the prototype's third status ("Suite generated") can't be
  // derived — ApplicationRead has no suite-generation flag — so this
  // approximates with the two states the API actually supports. Upgrade
  // once the backend tracks whether a suite has been generated.
  const statusLabel =
    application.discovery_status === 'completed' && (scenarioCount ?? 0) > 0
      ? 'Ready for suite'
      : 'Mapping in progress'

  return (
    <button
      type="button"
      onClick={onResume}
      className="card-panel home-app-card"
      style={{
        textAlign: 'left',
        borderColor: 'var(--border-hairline)',
        padding: '20px 22px',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        maxWidth: 360,
        width: '100%',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 'var(--space-5)',
          marginBottom: 'var(--space-7)',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            display: 'inline-flex',
            width: 42,
            height: 42,
            borderRadius: 10,
            background: 'var(--accent-wash)',
            color: 'var(--accent)',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <FolderIcon size={19} />
        </span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            background: 'var(--accent-wash)',
            color: 'var(--accent)',
            borderRadius: 'var(--radius-full)',
            padding: '4px 10px',
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          {statusLabel}
        </span>
      </div>
      <div
        style={{
          fontSize: 15,
          fontWeight: 700,
          marginBottom: 3,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {application.name}
      </div>
      <div
        className="caption"
        style={{ fontSize: 12.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
      >
        {journeyCount ?? '…'} journeys · {scenarioCount ?? '…'} scenarios
      </div>
    </button>
  )
}

export function Home({
  user,
  application,
  onConnectApp,
  onResumeApplication,
}: {
  user: UserRead
  application: ApplicationRead | null
  onConnectApp: () => void
  onResumeApplication: () => void
}) {
  const firstName = user.name.trim().split(/\s+/)[0]
  const [showDemo, setShowDemo] = useState(false)

  return (
    <main
      style={{
        width: '100%',
        boxSizing: 'border-box',
        height: 'calc(100vh - 64px)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        background:
          'radial-gradient(900px 500px at 85% -10%, var(--accent-wash-soft) 0%, transparent 55%), linear-gradient(180deg, #FBFCFE 0%, #F6F9FB 100%)',
      }}
    >
      <div
        style={{
          flex: 1,
          minWidth: 0,
          overflow: 'hidden',
          padding: '36px 44px',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-9)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 'var(--space-8)',
            flexShrink: 0,
            animation: 'aitg-fade-up 0.4s ease-out both',
          }}
        >
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>
              Welcome, {firstName}
            </div>
            <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.02em', margin: 0 }}>Projects</h1>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)', flexShrink: 0 }}>
            <button
              type="button"
              className="button-secondary"
              onClick={() => setShowDemo(true)}
              style={{ padding: '11px 18px' }}
            >
              Watch Demo
            </button>
          </div>
        </div>

        {application ? (
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', animation: 'aitg-fade-up 0.4s ease-out 0.1s both' }}>
            <ApplicationCard application={application} onResume={onResumeApplication} />
          </div>
        ) : (
          <div
            style={{
              border: '1px dashed var(--border)',
              borderRadius: 'var(--radius-xl)',
              boxSizing: 'border-box',
              padding: 'var(--space-10)',
              flex: 1,
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              animation: 'aitg-fade-up 0.4s ease-out 0.05s both',
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: 'inline-flex',
                width: 52,
                height: 52,
                borderRadius: 'var(--radius-full)',
                background: 'var(--accent-wash)',
                color: 'var(--accent)',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 'var(--space-8)',
                flexShrink: 0,
              }}
            >
              <FolderIcon size={24} />
            </span>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 'var(--space-3)' }}>No projects yet</div>
            <p className="caption" style={{ fontSize: 14, margin: '0 0 var(--space-8)', maxWidth: 420, lineHeight: 1.5 }}>
              Connect your first application to start discovering journeys and generating tests — no
              scripts required.
            </p>
            <button type="button" className="button-primary" onClick={onConnectApp} style={{ padding: '10px 20px' }}>
              + Create New Project
            </button>
          </div>
        )}
      </div>

      {showDemo && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Product demo"
          onClick={() => setShowDemo(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 'var(--space-9)',
            zIndex: 50,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="card-panel"
            style={{ maxWidth: 560, width: '100%', padding: 'var(--space-8)' }}
          >
            <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 4 }}>Product demo</div>
            <p className="caption" style={{ margin: '0 0 var(--space-7)' }}>
              Connect App → Discover Journeys → Review Scenarios → Generate Suite, in a few minutes.
            </p>
            <div
              style={{
                background: 'var(--ink)',
                borderRadius: 'var(--radius-lg)',
                aspectRatio: '16 / 9',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 'var(--space-7)',
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: 'var(--radius-full)',
                  background: 'rgba(255,255,255,0.12)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#FFFFFF',
                  fontSize: 20,
                }}
              >
                ▶
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button type="button" className="button-secondary" onClick={() => setShowDemo(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
