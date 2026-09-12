// Shared "{name} · {url}" line shown under every app-scoped page's title
// (Workspace's tabs, plus Journeys/Scenarios/Record and play which live
// outside Workspace.tsx) — keeps the app's identity visible and the title
// and URL on their own lines everywhere, instead of only on Workspace's tabs.
export function AppIdentityLine({ name, url }: { name: string; url: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--fg-3)', minWidth: 0 }}>
      <span style={{ fontWeight: 600, color: 'var(--fg-2)', flex: 'none' }}>{name}</span>
      <span style={{ width: 3, height: 3, borderRadius: 1000, background: 'var(--fg-6)', flex: 'none' }} />
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        style={{ color: 'var(--fg-4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
      >
        {url}
      </a>
    </div>
  )
}
