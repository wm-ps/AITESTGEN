import { useEffect, useMemo, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowRight, faBug, faChevronRight, faLayerGroup, faXmark } from '@fortawesome/free-solid-svg-icons'
import { EmptyState, ScreensIllustration } from '../components/EmptyState'
import { shotUrl, type AppMap, type ExplorerHealthIssue, type ExplorerScreen } from './explorerApi'
import { possibleBugs } from './HealthView'
import { glassCard } from './ui'

// A folded group shows this many screens until you ask for all of them.
const GROUP_PREVIEW = 8

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

// Screens grouped the way the app's menu groups them: by what they are about
// (Product offers, Price points, Rules…), in the order Explorer found them.
export function groupScreens(screens: ExplorerScreen[]): { name: string; screens: ExplorerScreen[] }[] {
  const groups = new Map<string, ExplorerScreen[]>()
  for (const s of inFoundOrder(screens)) {
    const name = s.view_kind === 'login' ? 'Sign in' : s.entity?.trim() || 'General'
    groups.set(name, [...(groups.get(name) ?? []), s])
  }
  return [...groups].map(([name, list]) => ({ name, screens: list }))
}

export function ScreensView({ map, issues = [], onOpenShot }: { map: AppMap | null; issues?: ExplorerHealthIssue[]; onOpenShot: (shotId: string, caption: string) => void }) {
  const screens = map?.screens ?? []
  const [query, setQuery] = useState('')
  // Groups you opened or folded; the first group starts open, the rest folded.
  const [toggled, setToggled] = useState<Set<string>>(new Set())
  const [showAll, setShowAll] = useState<Set<string>>(new Set())
  const [selected, setSelected] = useState<ExplorerScreen | null>(null)

  const q = query.trim().toLowerCase()
  const groups = useMemo(
    () => groupScreens(screens).map((g) => ({ ...g, screens: g.screens.filter((s) => !q || s.name.toLowerCase().includes(q)) })).filter((g) => g.screens.length),
    [screens, q],
  )
  const flip = (set: Set<string>, name: string) => {
    const next = new Set(set)
    if (!next.delete(name)) next.add(name)
    return next
  }

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
        <span style={{ fontSize: 13, color: 'var(--fg-3)' }}>{screens.length} screens found · click one to see how to get there and where it leads</span>
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

      {groups.length === 0 ? (
        <div style={{ ...glassCard, padding: 24, fontSize: 13.5, color: 'var(--fg-3)' }}>No screens match.</div>
      ) : (
        <div style={{ ...glassCard, padding: 0, overflow: 'hidden' }}>
          {groups.map((g, gi) => {
            // Searching opens every group that has a match.
            const open = q ? true : (gi === 0) !== toggled.has(g.name)
            const all = showAll.has(g.name)
            const visible = all ? g.screens : g.screens.slice(0, GROUP_PREVIEW)
            return (
              <section key={g.name} style={{ borderTop: gi ? '1px solid var(--line)' : 'none' }}>
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => setToggled((t) => flip(t, g.name))}
                  style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '13px 18px', border: 'none', background: 'transparent', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
                >
                  <FontAwesomeIcon icon={faChevronRight} style={{ fontSize: 10, color: 'var(--fg-5)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 150ms ease' }} />
                  <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: 'var(--fg)' }}>{g.name}</span>
                  <span style={{ fontSize: 12.5, color: 'var(--fg-5)' }}>{g.screens.length}</span>
                </button>
                {open && (
                  <div style={{ padding: '0 18px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 12 }}>
                      {visible.map((s) => (
                        <ScreenCard key={s.id} screen={s} problems={problemsOn(s, issues).length} onClick={() => setSelected(s)} />
                      ))}
                    </div>
                    {g.screens.length > GROUP_PREVIEW && (
                      <button type="button" className="button-secondary" style={{ alignSelf: 'flex-start', padding: '4px 10px', fontSize: 12 }} onClick={() => setShowAll((s) => flip(s, g.name))}>
                        {all ? 'Show fewer' : `Show all ${g.screens.length}`}
                      </button>
                    )}
                  </div>
                )}
              </section>
            )
          })}
        </div>
      )}
      {selected && map && <ScreenPanel screen={selected} map={map} problems={problemsOn(selected, issues).length} onPick={setSelected} onOpenShot={onOpenShot} onClose={() => setSelected(null)} />}
    </div>
  )
}

// Findings on a screen: the same screenshot, or the same page.
function problemsOn(screen: ExplorerScreen, issues: ExplorerHealthIssue[]): ExplorerHealthIssue[] {
  return possibleBugs(issues).filter((i) => (i.shot_id && i.shot_id === screen.shot_id) || i.url === screen.url)
}

function ScreenCard({ screen, problems, onClick }: { screen: ExplorerScreen; problems: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{ padding: 0, overflow: 'hidden', textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer', display: 'flex', flexDirection: 'column', border: '1px solid var(--line)', borderRadius: 10, background: 'white' }}
    >
      <span style={{ position: 'relative', display: 'block', aspectRatio: '16 / 10', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)' }}>
        {screen.shot_id ? (
          <img src={shotUrl(screen.shot_id)} alt={screen.name} loading="lazy" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} />
        ) : (
          <FontAwesomeIcon icon={faLayerGroup} style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', color: 'var(--fg-5)' }} />
        )}
      </span>
      <span style={{ padding: '8px 10px', display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span title={screen.name} style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{screen.name}</span>
        {/* Findings stay quiet: a small count, never a label over the image. */}
        {problems > 0 && <span title={`${problems} thing${problems === 1 ? '' : 's'} look wrong here`} style={{ flex: 'none', fontSize: 11.5, color: 'var(--fg-4)' }}><FontAwesomeIcon icon={faBug} style={{ fontSize: 10, marginRight: 4 }} />{problems}</span>}
      </span>
    </button>
  )
}

// One screen: how to get there, what you can press on it, and where each one takes you.
function ScreenPanel({
  screen,
  map,
  problems,
  onPick,
  onOpenShot,
  onClose,
}: {
  screen: ExplorerScreen
  map: AppMap
  problems: number
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
      {/* The whole screenshot fills the space left of the panel, so it reads without another click. */}
      <div style={{ flex: 1, minWidth: 0, padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {screen.shot_id && (
          <img
            key={screen.id}
            src={shotUrl(screen.shot_id)}
            alt={screen.name}
            title="Open full size"
            onClick={(e) => {
              e.stopPropagation()
              onOpenShot(screen.shot_id!, screen.name)
            }}
            style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: 10, boxShadow: '0 12px 40px rgba(15,23,42,0.3)', background: 'white', cursor: 'zoom-in', animation: 'aitg-fade-up 220ms ease' }}
          />
        )}
      </div>
      {/* The screenshot lives on the left, so the panel is only the way onward. */}
      <aside
        onClick={(e) => e.stopPropagation()}
        aria-label={screen.name}
        style={{ width: 'min(400px, 100vw)', height: '100%', background: 'white', boxShadow: '-12px 0 40px rgba(15,23,42,0.18)', display: 'flex', flexDirection: 'column', animation: 'aitg-fade-up 220ms ease' }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '18px 20px 14px', borderBottom: '1px solid var(--line)' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <h3 style={{ margin: 0, fontSize: 17, fontWeight: 650, color: 'var(--fg)' }}>{screen.name}</h3>
            {screen.reached_by && (
              <span style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>
                <span style={{ color: 'var(--fg-5)' }}>How to get here: </span>
                {plainAction(screen.reached_by)}
              </span>
            )}
            {problems > 0 && <span style={{ fontSize: 12, color: 'var(--fg-4)' }}>{problems} thing{problems === 1 ? '' : 's'} look wrong here: see What it learned</span>}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} style={{ width: 32, height: 32, flex: 'none', border: '1px solid var(--line)', borderRadius: 8, background: 'white', cursor: 'pointer', color: 'var(--fg-3)' }}>
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>
        <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto', flex: 1 }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', color: 'var(--fg-5)' }}>
            FROM THIS SCREEN{leads.length > 0 && ` · ${leads.length}`}
          </span>
          {leads.length === 0 && <span style={{ fontSize: 13, color: 'var(--fg-4)' }}>Explorer hasn’t moved on from this screen yet.</span>}
          {leads.map((e) => {
            const to = byId.get(e.to_id)!
            return (
              <button
                key={`${e.action}>${e.to_id}`}
                type="button"
                title={`Show ${to.name}`}
                onClick={() => onPick(to)}
                style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 8, border: '1px solid var(--line)', borderRadius: 10, background: 'white', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
              >
                <span style={{ width: 96, height: 60, flex: 'none', borderRadius: 6, border: '1px solid var(--line)', background: 'var(--bg-2)', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {to.shot_id ? (
                    <img src={shotUrl(to.shot_id)} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} />
                  ) : (
                    <FontAwesomeIcon icon={faLayerGroup} style={{ color: 'var(--fg-5)' }} />
                  )}
                </span>
                <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span style={{ fontSize: 12.5, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    Press <strong style={{ color: 'var(--fg)' }}>{plainAction(e.action)}</strong>
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <FontAwesomeIcon icon={faArrowRight} style={{ fontSize: 10, color: 'var(--fg-5)', flex: 'none' }} />
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--accent-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{to.name}</span>
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </aside>
    </div>
  )
}
