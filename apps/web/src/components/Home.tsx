import type { UserRead } from '../api'

const CARDS = [
  {
    key: 'new-project',
    icon: '+',
    title: 'Start a New Project',
    caption: 'Import an application and let AITestGen discover its journeys from scratch.',
    delay: 0.05,
  },
  {
    key: 'managed-applications',
    icon: '▤',
    title: 'Managed Applications',
    caption: 'Browse and manage every application connected to AITestGen.',
    delay: 0.1,
  },
  {
    key: 'product-demo',
    icon: '▶',
    title: 'Watch a Product Demo',
    caption: 'See the full Import → Discover → Validate → Generate flow in three minutes.',
    delay: 0.15,
  },
] as const

export function Home({ user, onConnectApp }: { user: UserRead; onConnectApp: () => void }) {
  const firstName = user.name.trim().split(/\s+/)[0]

  return (
    <main
      style={{
        maxWidth: 'var(--content-max)',
        margin: '0 auto',
        padding: '56px var(--content-x)',
      }}
    >
      <div style={{ marginBottom: 'var(--space-8)', animation: 'aitg-fade-up 0.4s ease-out both' }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em', margin: '0 0 6px' }}>
          Welcome back, {firstName}
        </h1>
        <p className="caption" style={{ fontSize: 15, margin: 0 }}>
          Pick up where you left off, or start something new.
        </p>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 'var(--space-5)',
        }}
      >
        {CARDS.map((card) => (
          <button
            key={card.key}
            type="button"
            className="card-panel card-clickable"
            onClick={card.key === 'product-demo' ? undefined : onConnectApp}
            style={{
              textAlign: 'left',
              padding: 'var(--space-6)',
              cursor: 'pointer',
              animation: `aitg-fade-up 0.4s ease-out ${card.delay}s both`,
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 40,
                height: 40,
                borderRadius: 'var(--radius-full)',
                background: 'var(--signal-wash)',
                color: 'var(--signal)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 18,
                fontWeight: 700,
                marginBottom: 'var(--space-4)',
              }}
            >
              {card.icon}
            </span>
            <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 'var(--space-2)' }}>{card.title}</div>
            <div className="caption" style={{ lineHeight: 1.5 }}>
              {card.caption}
            </div>
          </button>
        ))}
      </div>
    </main>
  )
}
