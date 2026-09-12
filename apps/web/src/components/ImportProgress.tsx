import { faRoute } from '@fortawesome/free-solid-svg-icons'
import { faIcon } from '../faIcon'

const Route = faIcon(faRoute)
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
      style={{
        background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
        backdropFilter: 'blur(16px) saturate(1.25)',
        border: '1px solid var(--border-1)',
        borderRadius: 14,
        boxShadow: 'var(--panel-shadow)',
        marginTop: 'var(--space-5)',
      }}
    >
      <GenerationLoader
        icon={Route}
        title="Mapping journeys…"
        body={`Vantage is crawling the deployed URL and grouping the crawl graph into journeys${applicationName ? ` in ${applicationName}` : ''}.`}
        bullets={['Crawling pages', 'Grouping flows', 'Capturing screenshots']}
        footer={
          <p className="caption" style={{ margin: '10px 0 0', fontSize: 12, opacity: 0.7 }}>
            Discovery runs in the background — this list updates automatically.
          </p>
        }
      />
    </div>
  )
}
