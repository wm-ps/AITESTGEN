import { GenerationLoader } from './GenerationLoader'

// Business-language import progress (FR-33, sprint-change-proposal-2026-07-21
// CR-2) — replaces the raw capture live-feed. No internal stage naming
// (Initialization/Authentication/Discovery/Analysis) is shown — the
// "Discovery in Progress" StatusPill already rendered above this component
// (DiscoverJourneys.tsx) is the page's one "in progress" indicator.
//
// Shares the same generation-loader animation as scenario/test-suite
// generation (GenerationLoader) rather than its own percent-fill progress
// bar — there's no reliable per-stage percent from the backend anyway, so a
// fixed number that jumps between a few values read as more precise than it
// was.
export function ImportProgress({ applicationName }: { applicationName?: string }) {
  return (
    <div
      className="card-panel"
      style={{
        padding: 'var(--space-10) var(--space-5)',
        marginTop: 'var(--space-5)',
      }}
    >
      <GenerationLoader
        title={`Discovering journeys${applicationName ? ` in ${applicationName}` : ''}`}
        footer={
          <p className="caption" style={{ margin: '6px 0 0', fontSize: 12, opacity: 0.7 }}>
            Discovery runs in the background — this list updates automatically.
          </p>
        }
      />
    </div>
  )
}
