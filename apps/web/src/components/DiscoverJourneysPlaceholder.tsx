import { Stepper } from './Stepper'

export function DiscoverJourneysPlaceholder({ discoveryStatus }: { discoveryStatus: string }) {
  return (
    <>
      <Stepper current="discover" />
      <main
        style={{
          maxWidth: 'var(--content-max)',
          margin: '0 auto',
          padding: `var(--content-top) var(--content-x)`,
        }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 650, margin: '0 0 8px' }}>Discover Journeys</h1>
        <p className="caption">
          Discovery Run status: {discoveryStatus}. This step is built out in Story 2.1.
        </p>
      </main>
    </>
  )
}
