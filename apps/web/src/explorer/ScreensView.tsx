import { useEffect, useMemo, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowRight, faLayerGroup, faXmark } from '@fortawesome/free-solid-svg-icons'
import { EmptyState, ScreensIllustration } from '../components/EmptyState'
import { shotUrl, type AppMap, type ExplorerScreen } from './explorerApi'
import { glassCard } from './ui'

// Big apps have hundreds of screens: a page of cards at a time, lazy images.
const PAGE = 48

// Icon alt text read out with a label ("Logout Icon Logout", "Icon") means
// nothing to a reader: keep the words, drop the icon, name a bare icon plainly.
export function plainAction(action: string | null | undefined): string {
  const text = (action || 'Continue').replace(/\b\w+ Icon\b\s*/gi, '').replace(/\bicon\b/gi, '').replace(/\s+/g, ' ').trim()
  return text || 'an unlabelled button'
}

// The order Explorer found them in (the API's order). Sign-in comes first:
// Explorer signs in before it starts reading screens, so its login page is
// often stored last even though it is where every visit begins.
export function inFoundOrder(screens: ExplorerScreen[]): ExplorerScreen[] {
  return [...screens].sort((a, b) => Number(b.view_kind === 'login') - Number(a.view_kind === 'login'))
}

export function ScreensView({ map, onOpenShot }: { map: AppMap | null; onOpenShot: (shotId: string, caption: string) => void }) {
  const screens = useMemo(() => inFoundOrder(map?.screens ?? []), [map])
  const [query, setQuery] = useState('')
  const [limit, setLimit] = useState(PAGE)
  const [selected, setSelected] = useState<ExplorerScreen | null>(null)

  const q = query.trim().toLowerCase()
  const shown = screens.filter((s) => !q || s.name.toLowerCase().includes(q))

  if (screens.length === 0) {
    return (
      <EmptyState
        variant="scene"
        illustration={<ScreensIllustration />}
        title="No screens yet"
        subtitle="Every screen Explorer finds shows up here with a screenshot, along with where each of its buttons leads."
      />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, color: 'var(--fg-3)' }}>{screens.length} screens</span>
        {/* Same look as every other Explorer field (no browser search styling). */}
        <input
          className="field"
          aria-label="Search screens"
          placeholder="Search screens by name"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ marginLeft: 'auto', width: 240, fontFamily: 'inherit', fontSize: 13, padding: '8px 10px' }}
        />
      </div>

      {shown.length === 0 ? (
        <div style={{ ...glassCard, padding: 24, fontSize: 13.5, color: 'var(--fg-3)' }}>No screens match.</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 16 }}>
          {shown.slice(0, limit).map((s, i) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setSelected(s)}
              style={{ ...glassCard, padding: 0, overflow: 'hidden', textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer', display: 'flex', flexDirection: 'column', animation: i < 24 ? `aitg-fade-up 320ms ease ${i * 25}ms both` : undefined }}
            >
              <span style={{ position: 'relative', display: 'block', aspectRatio: '16 / 10', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)' }}>
                {s.shot_id ? (
                  <img src={shotUrl(s.shot_id)} alt={s.name} loading="lazy" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} />
                ) : (
                  <FontAwesomeIcon icon={faLayerGroup} style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', color: 'var(--fg-5)' }} />
                )}
              </span>
              <span style={{ padding: '10px 12px 12px', display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                <span style={{ flex: 1, minWidth: 0, fontSize: 13.5, fontWeight: 600, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
              </span>
            </button>
          ))}
        </div>
      )}
      {shown.length > limit && (
        <button type="button" className="button-secondary" style={{ alignSelf: 'center' }} onClick={() => setLimit((n) => n + PAGE)}>
          Show {Math.min(PAGE, shown.length - limit)} more of {shown.length - limit}
        </button>
      )}
      {selected && map && <ScreenPanel screen={selected} map={map} onPick={setSelected} onOpenShot={onOpenShot} onClose={() => setSelected(null)} />}
    </div>
  )
}

// One screen: what you can press on it, and where each one takes you.
function ScreenPanel({
  screen,
  map,
  onPick,
  onOpenShot,
  onClose,
}: {
  screen: ExplorerScreen
  map: AppMap
  onPick: (s: ExplorerScreen) => void
  onOpenShot: (shotId: string, caption: string) => void
  onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const byId = new Map(map.screens.map((s) => [s.id, s]))
  const seen = new Set<string>()
  const leads = map.edges
    .filter((e) => e.from_id === screen.id && e.to_id !== screen.id && byId.has(e.to_id))
    .filter((e) => {
      const key = `${e.action}>${e.to_id}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(15,23,42,0.35)', display: 'flex', justifyContent: 'flex-end' }}>
      <aside
        onClick={(e) => e.stopPropagation()}
        aria-label={screen.name}
        style={{ width: 'min(520px, 100vw)', height: '100%', background: 'white', boxShadow: '-12px 0 40px rgba(15,23,42,0.18)', display: 'flex', flexDirection: 'column', animation: 'aitg-fade-up 220ms ease', overflowY: 'auto' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 20px', borderBottom: '1px solid var(--line)' }}>
          <h3 style={{ margin: 0, flex: 1, fontSize: 17, fontWeight: 650, color: 'var(--fg)' }}>{screen.name}</h3>
          <button type="button" aria-label="Close" onClick={onClose} style={{ width: 32, height: 32, border: '1px solid var(--line)', borderRadius: 8, background: 'white', cursor: 'pointer', color: 'var(--fg-3)' }}>
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>
        {screen.shot_id && (
          <img
            src={shotUrl(screen.shot_id)}
            alt={screen.name}
            onClick={() => onOpenShot(screen.shot_id!, screen.name)}
            style={{ width: '100%', aspectRatio: '16 / 10', objectFit: 'cover', objectPosition: 'top', cursor: 'zoom-in', borderBottom: '1px solid var(--line)' }}
          />
        )}
        <div style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', color: 'var(--fg-5)' }}>FROM THIS SCREEN</span>
          {leads.length === 0 && <span style={{ fontSize: 13, color: 'var(--fg-4)' }}>Explorer hasn’t moved on from this screen yet.</span>}
          {leads.map((e) => {
            const to = byId.get(e.to_id)!
            return (
              <button
                key={`${e.action}>${e.to_id}`}
                type="button"
                onClick={() => onPick(to)}
                style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 10, background: 'white', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
              >
                <span style={{ flex: 1, minWidth: 0, fontSize: 13, color: 'var(--fg-2)' }}>
                  Press <strong style={{ color: 'var(--fg)' }}>{plainAction(e.action)}</strong>
                </span>
                <FontAwesomeIcon icon={faArrowRight} style={{ fontSize: 11, color: 'var(--fg-5)' }} />
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, maxWidth: '50%' }}>
                  {to.shot_id && <img src={shotUrl(to.shot_id)} alt="" loading="lazy" style={{ width: 48, height: 30, flex: 'none', objectFit: 'cover', objectPosition: 'top', borderRadius: 5, border: '1px solid var(--line)' }} />}
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{to.name}</span>
                </span>
              </button>
            )
          })}
        </div>
      </aside>
    </div>
  )
}
