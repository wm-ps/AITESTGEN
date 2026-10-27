import { useState, type ReactNode } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import {
  faArrowRight,
  faBug,
  faChevronDown,
  faCircleCheck,
  faCompass,
  faDatabase,
  faKeyboard,
  faListCheck,
  faPaperPlane,
  faPlay,
  faRoute,
  faTriangleExclamation,
  faUserCheck,
} from '@fortawesome/free-solid-svg-icons'
import { EmptyState, ScenariosIllustration } from '../components/EmptyState'
import { LoadingDots, Spinner } from '../components/LoadingDots'
import { proofUrl, shotUrl, type ExplorerRun, type ExplorerScreen, type ExplorerTestCase } from './explorerApi'
import { glassCard, IconTile, Pill, type Tone } from './ui'

const STATUS: Record<string, { label: string; tone: Tone }> = {
  proven: { label: 'Works', tone: 'ok' },
  known_bug: { label: 'Possible bug', tone: 'warn' },
  building: { label: 'Trying it', tone: 'info' },
  planned: { label: 'Up next', tone: 'neutral' },
}

const KIND: Record<string, { label: string; icon: IconDefinition }> = {
  navigation: { label: 'Getting around', icon: faCompass },
  validation: { label: 'Input rules', icon: faKeyboard },
  error_state: { label: 'Error handling', icon: faTriangleExclamation },
  data_load: { label: 'Data shown', icon: faDatabase },
  form_submission: { label: 'Saving a form', icon: faPaperPlane },
  page_quality: { label: 'Page quality', icon: faListCheck },
  journey: { label: 'Whole journey', icon: faRoute },
}

const label = { fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', color: 'var(--fg-5)', marginBottom: 6, textTransform: 'uppercase' } as const

export function ScenariosView({
  run,
  tests,
  screens = [],
  onOpenShot,
  onGenerateTests,
  onVerdict,
}: {
  run: ExplorerRun
  tests: ExplorerTestCase[]
  screens?: ExplorerScreen[]
  onOpenShot: (shotId: string, caption: string) => void
  onGenerateTests?: () => Promise<void>
  onVerdict?: (testId: string, verdict: Verdict) => Promise<void>
}) {
  const [openId, setOpenId] = useState<string | null>(null)
  // Screens the user folded or unfolded; by default only the first is open.
  const [toggled, setToggled] = useState<Set<string>>(() => new Set())
  const [kindFilter, setKindFilter] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [video, setVideo] = useState<string | null>(null)
  // Dropped ones never held up in the app; they are not scenarios.
  const all = tests.filter((t) => t.status !== 'dropped').sort((a, b) => rank(a.status) - rank(b.status))
  const shown = kindFilter ? all.filter((t) => t.kind === kindFilter) : all
  const count = (items: ExplorerTestCase[], ...statuses: string[]) => items.filter((t) => statuses.includes(t.status)).length
  const works = count(all, 'proven')
  const bugs = count(all, 'known_bug')
  const trying = count(all, 'building', 'planned')
  const asked = all.filter((t) => t.trust === 'confirmed').length
  const kinds = [...new Set(all.map((t) => t.kind))]
  // Whole journeys first, in one group; then one group per screen (the Journey it lands in).
  const WHOLE = 'Whole journeys'
  const byScreen = new Map<string, ExplorerTestCase[]>()
  for (const t of shown) {
    const key = t.kind === 'journey' ? WHOLE : t.start_screen || 'Other'
    byScreen.set(key, [...(byScreen.get(key) ?? []), t])
  }
  // Screens with a bug first, then the busiest.
  const groups = [...byScreen.entries()].sort(
    ([ka, a], [kb, b]) => Number(kb === WHOLE) - Number(ka === WHOLE) || count(b, 'known_bug') - count(a, 'known_bug') || b.length - a.length,
  )
  const shotOf = new Map(screens.filter((s) => s.shot_id).map((s) => [s.name, s.shot_id!]))

  if (all.length === 0) {
    return run.status === 'testing' ? (
      <EmptyState
        variant="scene"
        illustration={<ScenariosIllustration />}
        title="Writing the scenarios"
        subtitle="Explorer is turning what it learned into scenarios and trying each one in the app. They appear here one by one."
        action={<LoadingDots label="Working" />}
      />
    ) : (
      <EmptyState
        variant="scene"
        illustration={<ScenariosIllustration />}
        title="No scenarios yet"
        subtitle="Once Explorer has tried every path, it writes the scenarios worth testing and proves each one in the app before it shows here."
      />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* What's ready, at a glance */}
      <section style={{ ...glassCard, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 22, flexWrap: 'wrap' }}>
          <Stat value={works} label="work as they should" tone="ok" icon={faCircleCheck} />
          {bugs > 0 && <Stat value={bugs} label={bugs === 1 ? 'possible bug to check' : 'possible bugs to check'} tone="warn" icon={faBug} />}
          {trying > 0 && <Stat value={trying} label="still being tried" tone="info" />}
          {asked > 0 && <Stat value={asked} label="from what you told Explorer" tone="accent" icon={faUserCheck} />}
          <span style={{ flex: 1 }} />
          {run.status === 'tested' && onGenerateTests && works > 0 && (
            <button
              type="button"
              className="button-primary"
              disabled={generating}
              onClick={async () => {
                setGenerating(true)
                try {
                  await onGenerateTests()
                } finally {
                  setGenerating(false)
                }
              }}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, animation: generating ? undefined : 'explorer-attention 1.8s ease-out infinite' }}
            >
              {generating ? <LoadingDots label="Starting" /> : (<>Generate tests <FontAwesomeIcon icon={faArrowRight} style={{ fontSize: 11 }} /></>)}
            </button>
          )}
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>
          Each scenario was tried in the app and replayed until it gave the same result every time.
          {run.status === 'tested' && ' Generate tests turns the working ones into Playwright tests you can run.'}
          {bugs > 0 && ' A possible bug never becomes a test case: open it and choose Not a bug (keep it as a test) or Ignore.'}
        </div>
        {kinds.length > 1 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <Chip active={kindFilter === null} onClick={() => setKindFilter(null)}>All · {all.length}</Chip>
            {kinds.map((k) => (
              <Chip key={k} active={kindFilter === k} onClick={() => setKindFilter(kindFilter === k ? null : k)} icon={KIND[k]?.icon}>
                {KIND[k]?.label ?? k} · {all.filter((t) => t.kind === k).length}
              </Chip>
            ))}
          </div>
        )}
      </section>

      {groups.map(([screen, items], g) => {
        const open = toggled.has(screen) !== (g === 0)
        const works = count(items, 'proven')
        const bugs = count(items, 'known_bug')
        const trying = count(items, 'building', 'planned')
        const shot = shotOf.get(screen)
        return (
          <section key={screen} style={{ ...glassCard, padding: 0, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', background: open ? 'color-mix(in srgb, var(--accent-wash) 45%, transparent)' : 'transparent', transition: 'background 150ms ease' }}>
            <button
              type="button"
              aria-label={`Open the screenshot of ${screen}`}
              disabled={!shot}
              onClick={() => shot && onOpenShot(shot, screen)}
              style={{ width: 72, aspectRatio: '16 / 10', flex: 'none', margin: '12px 0 12px 16px', padding: 0, borderRadius: 7, overflow: 'hidden', background: 'var(--bg-2)', border: '1px solid var(--line)', cursor: shot ? 'zoom-in' : 'default' }}
            >
              {shot && <img src={shotUrl(shot)} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top', display: 'block' }} />}
            </button>
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setToggled((prev) => { const next = new Set(prev); if (next.has(screen)) next.delete(screen); else next.add(screen); return next })}
              style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px 12px 14px', border: 'none', background: 'transparent', cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit' }}
            >
              <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 15, fontWeight: 650, color: 'var(--fg)' }}>{screen}</span>
                <span style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>{items.length} scenario{items.length === 1 ? '' : 's'}</span>
              </span>
              <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {bugs > 0 && <Pill tone="warn" icon={faBug}>{bugs} possible bug{bugs === 1 ? '' : 's'}</Pill>}
                {works > 0 && <Pill tone="ok" icon={faCircleCheck}>{works} work{works === 1 ? 's' : ''}</Pill>}
                {trying > 0 && <Pill tone="info">{trying} trying</Pill>}
              </span>
              <FontAwesomeIcon icon={faChevronDown} style={{ fontSize: 11, color: 'var(--fg-5)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }} />
            </button>
            </div>
            {open && items.map((t, i) => {
              const status = STATUS[t.status] ?? STATUS.planned
              const kind = KIND[t.kind] ?? { label: t.kind, icon: faListCheck }
              const isOpen = openId === t.id
              return (
                <div key={t.id} style={{ borderTop: '1px solid var(--line)', animation: i < 20 ? `aitg-fade-up 240ms ease ${i * 25}ms both` : undefined, opacity: t.status === 'planned' ? 0.7 : 1, background: isOpen ? 'rgba(255,255,255,0.6)' : undefined }}>
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    onClick={() => setOpenId(isOpen ? null : t.id)}
                    style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 14, padding: '11px 16px 11px 30px', border: 'none', background: 'transparent', cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit' }}
                  >
                    {t.status === 'building' ? (
                      <span style={{ width: 34, height: 34, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}><Spinner size={14} /></span>
                    ) : (
                      <IconTile icon={kind.icon} tone={t.status === 'known_bug' ? 'warn' : t.status === 'proven' ? 'accent' : 'neutral'} size={34} />
                    )}
                    <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
                      <span style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--fg)' }}>{t.title}</span>
                      {t.purpose && (
                        <span style={{ fontSize: 12.5, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.purpose}</span>
                      )}
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--fg-5)', flexWrap: 'wrap' }}>
                        {t.coverage && (
                          <span title={t.linked_to ? `Linked to ${t.linked_to}` : 'Checklist item it covers'} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: 'var(--accent-2)' }}>
                            {t.coverage.split(' ')[0]}
                            {t.linked_to ? ` → ${t.linked_to}` : ''}
                          </span>
                        )}
                        <span>{kind.label}</span>
                        <span>·</span>
                        <span>{t.steps.length} step{t.steps.length === 1 ? '' : 's'}</span>
                        {t.trust === 'confirmed' && <Pill tone="accent" icon={faUserCheck}>You asked for this</Pill>}
                      </span>
                    </span>
                    <Pill tone={status.tone}>{status.label}</Pill>
                    <FontAwesomeIcon icon={faChevronDown} style={{ fontSize: 11, color: 'var(--fg-5)', transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }} />
                  </button>
                  {isOpen && (
                    <div style={{ padding: '4px 18px 16px 78px', display: 'flex', gap: 24, flexWrap: 'wrap', animation: 'aitg-fade-up 200ms ease' }}>
                      <div style={{ flex: '2 1 320px', minWidth: 0 }}>
                        <div style={label}>Steps</div>
                        <ol style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13, color: 'var(--fg-2)' }}>
                          {t.steps.map((step, k) => (
                            <li key={k}>{step}</li>
                          ))}
                        </ol>
                      </div>
                      <div style={{ flex: '1 1 260px', display: 'flex', flexDirection: 'column', gap: 12, fontSize: 13, minWidth: 0 }}>
                        <div>
                          <div style={label}>Should happen</div>
                          <div style={{ color: 'var(--fg-2)' }}>{t.expected}</div>
                        </div>
                        {t.status === 'known_bug' && t.observed && (
                          <div>
                            <div style={{ ...label, color: 'var(--warn-2)' }}>The app did</div>
                            <div style={{ color: 'var(--fg-2)' }}>{t.observed}</div>
                          </div>
                        )}
                        {t.status === 'known_bug' && onVerdict && <VerdictButtons testId={t.id} onVerdict={onVerdict} />}
                        {t.proof_runs > 0 && (
                          <div style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>
                            Same result in {t.proof_passes} of {t.proof_runs} replays
                            {t.catches_breakage ? ', and it fails when the key step is left out.' : '.'}
                          </div>
                        )}
                        {t.evidence_shot_id && (
                          <img
                            src={shotUrl(t.evidence_shot_id)}
                            alt="The screen at the end of the scenario"
                            onClick={() => onOpenShot(t.evidence_shot_id!, t.title)}
                            style={{ width: '100%', maxWidth: 320, aspectRatio: '16 / 10', objectFit: 'cover', objectPosition: 'top', borderRadius: 10, border: '1px solid var(--line)', cursor: 'zoom-in' }}
                          />
                        )}
                        {t.has_proof_video && (
                          <button type="button" onClick={() => setVideo(video === t.id ? null : t.id)} style={{ ...linkButton, display: 'inline-flex', alignItems: 'center', gap: 6, alignSelf: 'flex-start' }}>
                            <FontAwesomeIcon icon={faPlay} style={{ fontSize: 10 }} /> {video === t.id ? 'Hide recording' : 'Watch it run'}
                          </button>
                        )}
                        {video === t.id && <video src={proofUrl(t.id)} controls autoPlay muted style={{ width: '100%', borderRadius: 10, border: '1px solid var(--line)' }} />}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </section>
        )
      })}
    </div>
  )
}

type Verdict = 'not_a_bug' | 'ignore'

function VerdictButtons({ testId, onVerdict }: { testId: string; onVerdict: (testId: string, verdict: Verdict) => Promise<void> }) {
  const [busy, setBusy] = useState<Verdict | null>(null)
  const send = async (verdict: Verdict) => {
    setBusy(verdict)
    try {
      await onVerdict(testId, verdict)
    } finally {
      setBusy(null)
    }
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 12px', borderRadius: 10, background: 'color-mix(in srgb, var(--warn-2) 7%, white)', border: '1px solid color-mix(in srgb, var(--warn-2) 22%, transparent)' }}>
      <div style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>Is what the app did correct?</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className="button-primary" disabled={busy !== null} onClick={() => void send('not_a_bug')} style={{ padding: '6px 12px', fontSize: 12.5 }}>
          {busy === 'not_a_bug' ? <LoadingDots label="Saving" /> : 'Not a bug, keep as a test'}
        </button>
        <button type="button" className="button-secondary" disabled={busy !== null} onClick={() => void send('ignore')} style={{ padding: '6px 12px', fontSize: 12.5 }}>
          {busy === 'ignore' ? <LoadingDots label="Saving" /> : 'Ignore'}
        </button>
      </div>
    </div>
  )
}

function Stat({ value, label: text, tone, icon }: { value: number; label: string; tone: Tone; icon?: IconDefinition }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
      {icon && <IconTile icon={icon} tone={tone} size={30} />}
      <span style={{ display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontSize: 20, fontWeight: 700, color: 'var(--fg)', lineHeight: '24px' }}>{value}</span>
        <span style={{ fontSize: 12, color: 'var(--fg-4)' }}>{text}</span>
      </span>
    </span>
  )
}

function Chip({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon?: IconDefinition; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 11px',
        borderRadius: 1000,
        fontSize: 12.5,
        fontWeight: 600,
        fontFamily: 'inherit',
        cursor: 'pointer',
        color: active ? 'var(--accent-2)' : 'var(--fg-3)',
        background: active ? 'var(--accent-wash)' : 'transparent',
        border: `1px solid ${active ? 'color-mix(in srgb, var(--accent-2) 30%, transparent)' : 'var(--line)'}`,
      }}
    >
      {icon && <FontAwesomeIcon icon={icon} style={{ fontSize: 10 }} />}
      {children}
    </button>
  )
}

const linkButton = { border: 'none', background: 'none', padding: 0, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, color: 'var(--accent-2)' } as const

function rank(status: string) {
  return { known_bug: 0, proven: 1, building: 2, planned: 3 }[status] ?? 4
}
