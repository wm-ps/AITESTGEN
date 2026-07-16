const CARDS = [
  {
    key: 'new-project',
    title: 'Start a New Project',
    caption: 'Register a new Application and begin Discovery.',
  },
  {
    key: 'managed-applications',
    title: 'Managed Applications',
    caption: 'Connect an Application to this workspace.',
  },
  {
    key: 'product-demo',
    title: 'Watch a Product Demo',
    caption: 'See how discovery, review, and generation fit together.',
  },
] as const

export function Home({ onConnectApp }: { onConnectApp: () => void }) {
  return (
    <main
      style={{
        maxWidth: 'var(--content-max)',
        margin: '0 auto',
        padding: `var(--content-top) var(--content-x)`,
      }}
    >
      <h1 style={{ fontSize: 32, fontWeight: 650, letterSpacing: '-0.02em', margin: '0 0 24px' }}>
        Home
      </h1>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 'var(--space-4)',
        }}
      >
        {CARDS.map((card) => (
          <button
            key={card.key}
            type="button"
            className="card-panel"
            onClick={card.key === 'product-demo' ? undefined : onConnectApp}
            disabled={card.key === 'product-demo'}
            style={{
              textAlign: 'left',
              padding: 'var(--space-5)',
              cursor: card.key === 'product-demo' ? 'default' : 'pointer',
              opacity: card.key === 'product-demo' ? 0.6 : 1,
            }}
          >
            <div style={{ fontWeight: 650, fontSize: 15, marginBottom: 'var(--space-2)' }}>
              {card.title}
            </div>
            <div className="caption">{card.caption}</div>
          </button>
        ))}
      </div>
    </main>
  )
}
