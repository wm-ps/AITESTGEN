// Business-language import progress (FR-33, sprint-change-proposal-2026-07-21
// CR-2) — replaces the raw capture live-feed. No internal stage naming
// (Initialization/Authentication/Discovery/Analysis) is shown — the "Running"
// StatusPill already rendered above this component (DiscoverJourneys.tsx) is
// the page's one "in progress" indicator; this only needs the fill + percent.
//
// `[UPDATED 2026-07-21, live UX correction]` The percentage shown while a
// stage is IN PROGRESS is the percentage of the stage that just FINISHED —
// not that stage's own target. Pairing "Discovery" (in progress, potentially
// the longest stage by far) with 75% made it look nearly done the instant
// crawling started; now it shows 25% (authentication's completion) while
// discovering, and jumps to 75% only once discovery finishes and analysis
// begins. 100% is never rendered here — Journeys appear and this component
// unmounts before analysis itself would report as finished.
const STAGE_PERCENT: Record<string, number> = {
  initializing: 0,
  authenticating: 10,
  discovering: 25,
  analyzing: 75,
}

export function ImportProgress({
  stage,
  applicationName,
}: {
  stage: string | null
  applicationName?: string
}) {
  const percent = (stage && STAGE_PERCENT[stage]) ?? STAGE_PERCENT.initializing

  return (
    <div
      className="card-panel"
      style={{
        padding: 'var(--space-10) var(--space-5)',
        marginTop: 'var(--space-5)',
        textAlign: 'center',
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 'var(--space-6)' }}>
        Discovering journeys{applicationName ? ` in ${applicationName}` : ''}
      </div>
      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Import progress"
        style={{
          position: 'relative',
          maxWidth: 320,
          margin: '0 auto',
          height: 8,
          borderRadius: 'var(--radius-full)',
          background: 'var(--border)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${percent}%`,
            height: '100%',
            borderRadius: 'var(--radius-full)',
            background: 'var(--signal)',
            transition: 'width 400ms ease',
          }}
        />
        {/* Reuses the shimmer sweep already established in SignIn.tsx (same
            `aitg-shimmer-sweep` keyframe) so the bar reads as actively working,
            not stalled, between the fixed percentage jumps. */}
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(100deg, transparent 0%, rgba(255,255,255,0.65) 50%, transparent 100%)',
            animation: 'aitg-shimmer-sweep 1.8s ease-in-out infinite',
          }}
        />
      </div>
      <div className="caption" style={{ fontSize: 12, marginTop: 'var(--space-2)' }}>
        {percent}%
      </div>
    </div>
  )
}
