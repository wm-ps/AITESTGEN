import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import {
  faArrowRight,
  faBug,
  faCheck,
  faCircleExclamation,
  faCircleQuestion,
  faEye,
  faFileLines,
  faFlag,
  faHandPointRight,
  faLightbulb,
  faPause,
} from '@fortawesome/free-solid-svg-icons'
import { Spinner } from '../components/LoadingDots'
import {
  shotUrl,
  WORKING_STATUSES,
  type ExplorerEvent,
  type ExplorerEventKind,
  type ExplorerMission,
  type ExplorerQuestion,
  type ExplorerRun,
  type ExplorerScreen,
  type ExplorerTestCase,
} from './explorerApi'
import { glassCard, IconTile, timeAgo, type Tone } from './ui'

export type ExplorerView = 'live' | 'questions' | 'screens' | 'scenarios' | 'summary'

// Four stages a person can follow — the worker's finer statuses fold into them.
const STAGES: { label: string; statuses: string[] }[] = [
  { label: 'Learning the app', statuses: ['queued', 'signing_in', 'understanding', 'summarizing'] },
  { label: 'Your check', statuses: ['awaiting_confirmation', 'expired'] },
  { label: 'Trying every path', statuses: ['confirmed', 'planning', 'exploring', 'explored', 'hunting'] },
  { label: 'Writing scenarios', statuses: ['testing'] },
]

const KIND_STYLE: Record<ExplorerEventKind, { icon: IconDefinition; tone: Tone }> = {
  screen: { icon: faEye, tone: 'accent' },
  thought: { icon: faLightbulb, tone: 'info' },
  action: { icon: faHandPointRight, tone: 'neutral' },
  health: { icon: faBug, tone: 'warn' },
  phase: { icon: faFlag, tone: 'neutral' },
  summary: { icon: faFileLines, tone: 'ok' },
  error: { icon: faCircleExclamation, tone: 'bad' },
  question: { icon: faCircleQuestion, tone: 'warn' },
}
// The log: what it did and decided. Its running commentary and bug guesses stay out.
const LOGGED: ExplorerEventKind[] = ['action', 'screen', 'phase', 'summary', 'error', 'question']
const SCREEN_PREFIX = /^(On|Understood:|Reading:|Went to)\s+/

const minutesBetween = (from: string, to: string | number) =>
  Math.max(1, Math.round(((typeof to === 'number' ? to : new Date(to).getTime()) - new Date(from).getTime()) / 60000))

export function LiveView({
  run,
  events,
  questions,
  missions,
  tests,
  screens,
  applicationUrl,
  onOpenShot,
  onGoTo,
  onSkipMission,
}: {
  run: ExplorerRun
  events: ExplorerEvent[]
  questions: ExplorerQuestion[] | null
  missions: ExplorerMission[]
  tests: ExplorerTestCase[]
  screens: ExplorerScreen[]
  applicationUrl: string
  onOpenShot: (shotId: string, caption: string) => void
  onGoTo: (view: ExplorerView) => void
  onSkipMission: (missionId: string) => Promise<void>
}) {
  const working = WORKING_STATUSES.includes(run.status)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5000)
    return () => clearInterval(t)
  }, [])

  // The live frame follows the newest screenshot unless you pick one from the trail.
  const [pinned, setPinned] = useState<ExplorerEvent | null>(null)
  const trail = useMemo(() => {
    const seen = new Set<string>()
    const out: ExplorerEvent[] = []
    for (let i = events.length - 1; i >= 0 && out.length < 6; i--) {
      const e = events[i]
      if (e.shot_id && !seen.has(e.shot_id)) {
        seen.add(e.shot_id)
        out.push(e)
      }
    }
    return out
  }, [events])
  const shown = pinned ?? trail[0] ?? null
  const latest = events[events.length - 1] ?? null
  const shownName = shown?.title.replace(SCREEN_PREFIX, '') ?? ''
  const shownUrl = screens.find((s) => s.name === shownName)?.url ?? applicationUrl
  const mission = missions.find((m) => m.status === 'running' || m.status === 'waiting')

  // Only questions Explorer is actually waiting on; "is this a bug?" ones sit with the bugs.
  const open = (questions ?? []).filter((q) => q.status === 'open' && q.kind !== 'rule')
  const failed = run.status === 'failed' || run.status === 'stopped' || run.status === 'paused' || run.status === 'expired'
  const finished = run.status === 'tested'
  const stage = STAGES.findIndex((s) => s.statuses.includes(run.status))
  const at = (title: string) => events.find((e) => e.title.startsWith(title))?.created_at
  const summaryReady = at('App Summary is ready')
  const confirmedAt = at('App Summary confirmed')
  const scenariosStart = at('Working out scenarios')
  const scenarios = tests.filter((t) => t.status === 'proven' || t.status === 'known_bug')
  const [allMissions, setAllMissions] = useState(false)
  const [skipping, setSkipping] = useState<string | null>(null)
  const sortedMissions = [...missions].sort((a, b) => order(a.status) - order(b.status))
  const missionsShown = allMissions ? sortedMissions : sortedMissions.slice(0, 3)
  const activity = useMemo(() => [...events].reverse().filter((e) => LOGGED.includes(e.kind)).slice(0, 80), [events])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {(run.status === 'awaiting_confirmation' || open.length > 0) && (
        <div
          style={{
            borderRadius: 14,
            padding: '16px 18px',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            background: 'linear-gradient(135deg, color-mix(in srgb, var(--warn-2) 10%, white), color-mix(in srgb, var(--warn-2) 4%, white))',
            border: '1px solid color-mix(in srgb, var(--warn-2) 35%, transparent)',
            animation: 'aitg-fade-up 300ms ease, explorer-attention 1.8s ease-out 300ms infinite',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5, fontWeight: 700, letterSpacing: '0.07em', color: 'var(--warn-2)' }}>
            <FontAwesomeIcon icon={faPause} style={{ fontSize: 10 }} />
            WAITING FOR YOU
          </div>
          {run.status === 'awaiting_confirmation' ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <span style={{ flex: 1, minWidth: 240, fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>
                Explorer has learned the app. Check its summary and confirm so it can carry on.
              </span>
              <button type="button" className="button-primary" onClick={() => onGoTo('summary')}>
                Check the summary
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <span style={{ flex: 1, minWidth: 240, display: 'flex', flexDirection: 'column', gap: 3 }}>
                <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>{open[0].question.replace(/^I need this to continue: /, '')}</span>
                {open.length > 1 && <span style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>and {open.length - 1} more</span>}
              </span>
              <button type="button" className="button-primary" onClick={() => onGoTo('questions')}>
                Answer now
              </button>
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'stretch' }}>
        {/* The live browser */}
        <section aria-label="Live view" style={{ ...glassCard, padding: 0, overflow: 'hidden', flex: '2 1 560px', minWidth: 0, alignSelf: 'flex-start' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 14px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)' }}>
            <span aria-hidden style={{ display: 'flex', gap: 6 }}>
              {[0, 1, 2].map((i) => (
                <span key={i} style={{ width: 10, height: 10, borderRadius: 1000, background: 'var(--border-2)' }} />
              ))}
            </span>
            <span style={{ flex: 1, minWidth: 0, fontFamily: 'var(--font-mono, ui-monospace, monospace)', fontSize: 12, color: 'var(--fg-3)', background: 'white', border: '1px solid var(--line)', borderRadius: 7, padding: '5px 10px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {shownUrl.replace(/^https?:\/\//, '')}
            </span>
            {pinned ? (
              <button type="button" className="button-secondary" style={{ padding: '3px 10px', fontSize: 12 }} onClick={() => setPinned(null)}>
                Back to live
              </button>
            ) : working ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 700, letterSpacing: '0.07em', color: 'var(--bad)' }}>
                <span style={{ width: 8, height: 8, borderRadius: 1000, background: 'var(--bad)', animation: 'v2-pulse 1.4s ease-in-out infinite' }} />
                LIVE
              </span>
            ) : null}
          </div>
          <div
            style={{ position: 'relative', aspectRatio: '16 / 10', background: 'var(--bg-2)', cursor: shown?.shot_id ? 'zoom-in' : 'default', overflow: 'hidden' }}
            onClick={() => shown?.shot_id && onOpenShot(shown.shot_id, shown.title)}
          >
            {shown?.shot_id ? (
              <img key={shown.shot_id} src={shotUrl(shown.shot_id)} alt={shown.title} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top', animation: 'aitg-fade-up 360ms ease' }} />
            ) : (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, color: 'var(--fg-4)', fontSize: 13 }}>
                {working && <Spinner size={14} />}
                {working ? 'Opening the app…' : 'No screens captured'}
              </div>
            )}
            {working && !pinned && (
              <span
                aria-hidden
                style={{ position: 'absolute', inset: 0, pointerEvents: 'none', background: 'linear-gradient(180deg, transparent 0%, color-mix(in srgb, var(--accent-2) 14%, transparent) 50%, transparent 100%) no-repeat', backgroundSize: '100% 22%', animation: 'explorer-scan 3.6s linear infinite' }}
              />
            )}
            {(pinned ?? latest) && (
              <div style={{ position: 'absolute', left: 14, right: 14, bottom: 14, background: 'rgba(15, 30, 29, 0.86)', backdropFilter: 'blur(8px)', color: 'white', borderRadius: 12, padding: '11px 14px', display: 'flex', gap: 12, alignItems: 'center' }}>
                <span style={{ width: 28, height: 28, flex: 'none', borderRadius: 1000, background: 'var(--accent-2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                  {working && !pinned ? <Spinner size={12} /> : <FontAwesomeIcon icon={faArrowRight} style={{ fontSize: 12 }} />}
                </span>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                  <span key={(pinned ?? latest)!.id} style={{ fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', animation: 'aitg-fade-up 260ms ease' }}>
                    {(pinned ?? latest)!.title}
                  </span>
                  {mission && !pinned && <span style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.68)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Mission: {mission.title}</span>}
                </span>
              </div>
            )}
          </div>
          <div style={{ padding: '12px 14px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', color: 'var(--fg-5)' }}>JUST VISITED</span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 8 }}>
              {trail.map((e) => {
                const active = shown?.id === e.id
                return (
                  <button
                    key={e.id}
                    type="button"
                    title={e.title}
                    onClick={() => setPinned(e === trail[0] ? null : e)}
                    style={{ padding: 3, borderRadius: 9, border: `2px solid ${active ? 'var(--accent-2)' : 'transparent'}`, background: 'white', cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit', minWidth: 0 }}
                  >
                    <img src={shotUrl(e.shot_id!)} alt="" loading="lazy" style={{ width: '100%', aspectRatio: '16 / 10', objectFit: 'cover', objectPosition: 'top', display: 'block', borderRadius: 6, border: '1px solid var(--line)' }} />
                    <span style={{ display: 'block', fontSize: 11, color: 'var(--fg-3)', paddingTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.title.replace(SCREEN_PREFIX, '')}</span>
                  </button>
                )
              })}
            </div>
          </div>
        </section>

        {/* `contain: size` keeps this column from growing the row: it ends
            exactly where the live view ends, and the log scrolls inside. */}
        <div style={{ flex: '1 1 360px', minWidth: 0, minHeight: 540, contain: 'size', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* The log: what it just did, newest first */}
        <section aria-label="Activity log" style={{ ...glassCard, padding: '14px 0 6px', display: 'flex', flexDirection: 'column', flex: '1 1 0', minHeight: 0 }}>
          <div style={{ padding: '0 16px 8px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ flex: 1, fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', color: 'var(--fg-5)' }}>ACTIVITY</span>
            {working && <span style={{ width: 6, height: 6, borderRadius: 1000, background: 'var(--accent-2)', animation: 'v2-pulse 1.4s ease-in-out infinite' }} />}
          </div>
          <div style={{ overflowY: 'auto', padding: '0 10px 6px', display: 'flex', flexDirection: 'column' }}>
            {activity.length === 0 && (
              <div style={{ padding: '16px 8px', fontSize: 13, color: 'var(--fg-4)', display: 'flex', gap: 8, alignItems: 'center' }}>
                {working && <Spinner size={12} />} Starting up…
              </div>
            )}
            {activity.map((event, i) => {
              const style = KIND_STYLE[event.kind] ?? KIND_STYLE.thought
              return (
                <button
                  key={event.id}
                  type="button"
                  disabled={!event.shot_id}
                  onClick={() => event.shot_id && setPinned(event)}
                  style={{ display: 'flex', gap: 10, padding: '7px 6px', border: 'none', borderRadius: 8, background: shown?.id === event.id ? 'var(--accent-wash)' : 'transparent', textAlign: 'left', fontFamily: 'inherit', cursor: event.shot_id ? 'pointer' : 'default', animation: i === 0 && working ? 'aitg-fade-up 300ms ease' : undefined }}
                >
                  <IconTile icon={style.icon} tone={style.tone} size={24} />
                  <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <span style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                      <span style={{ flex: 1, fontSize: 12.5, fontWeight: 600, color: 'var(--fg-2)', lineHeight: '18px' }}>{event.title}</span>
                      <span style={{ fontSize: 11, color: 'var(--fg-5)', whiteSpace: 'nowrap' }}>{timeAgo(event.created_at, now)}</span>
                    </span>
                    {/* "Filled in 3 fields" says nothing; what was filled in does. */}
                    {event.detail && (
                      <span style={{ fontSize: 12, color: 'var(--fg-4)', lineHeight: '17px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={event.detail}>
                        {event.detail}
                      </span>
                    )}
                  </span>
                </button>
              )
            })}
          </div>
        </section>

        {/* Where it is, with what each stage produced */}
        <aside aria-label="Progress" style={{ ...glassCard, padding: '18px 18px 16px', boxSizing: 'border-box', flex: 'none' }}>
          <Stage
            index={0}
            current={stage}
            failed={failed}
            finished={finished}
            working={working}
            title={STAGES[0].label}
            detail={
              summaryReady
                ? `${run.counts.screens} screens · ${run.brief?.key_tasks?.length ?? 0} key tasks · ${minutesBetween(run.created_at, summaryReady)} min`
                : `${run.counts.screens} screens so far`
            }
          />
          <Stage
            index={1}
            current={stage}
            failed={failed}
            finished={finished}
            working={working}
            title={STAGES[1].label}
            detail={run.status === 'expired' ? 'Expired: the summary was not confirmed within 14 days' : confirmedAt ? `You approved the summary ${timeAgo(confirmedAt, now)}` : summaryReady ? 'Waiting for you to confirm the summary' : 'Comes after learning the app'}
          >
            {confirmedAt && (
              <button type="button" onClick={() => onGoTo('summary')} style={linkButton}>
                Read it again
              </button>
            )}
          </Stage>
          <Stage
            index={2}
            current={stage}
            failed={failed}
            finished={finished}
            working={working}
            title={missions.length ? `${STAGES[2].label} · ${run.counts.missions_done} of ${run.counts.missions_total}` : STAGES[2].label}
            detail={
              run.status === 'hunting'
                ? 'Looking for screens that only show up sometimes'
                : confirmedAt && (scenariosStart || stage > 2 || finished)
                  ? `${minutesBetween(confirmedAt, scenariosStart ?? now)} min`
                  : missions.length
                    ? ''
                    : 'Plans what to try once you confirm'
            }
          >
            {missions.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
                <div style={{ height: 6, borderRadius: 3, background: 'var(--chip)', overflow: 'hidden' }}>
                  <div style={{ width: `${(100 * run.counts.missions_done) / Math.max(1, run.counts.missions_total)}%`, height: '100%', background: 'var(--accent-2)', transition: 'width 600ms ease' }} />
                </div>
                {missionsShown.map((m) => {
                  const live = m.status === 'running' || m.status === 'waiting'
                  // Skip is always offered on the mission in progress; on
                  // queued ones once the full list is open.
                  const skippable = live || (allMissions && m.status === 'queued')
                  return (
                    <span key={m.id} style={{ display: 'flex', gap: 8, alignItems: 'baseline', fontSize: 12.5, color: live ? 'var(--fg)' : m.status === 'queued' ? 'var(--fg-5)' : 'var(--fg-3)', fontWeight: m.status === 'running' ? 600 : 400 }}>
                      <span style={{ width: 12, flex: 'none', textAlign: 'center' }}>{missionMark(m.status)}</span>
                      <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={m.title}>{m.title}</span>
                      {skippable && (
                        <button
                          type="button"
                          disabled={skipping === m.id}
                          title={live ? 'Stop this mission and move on to the next one' : 'Leave this mission out'}
                          onClick={async () => {
                            setSkipping(m.id)
                            try {
                              await onSkipMission(m.id)
                            } finally {
                              setSkipping(null)
                            }
                          }}
                          style={{ ...linkButton, flex: 'none', fontSize: 12, fontWeight: 600, color: live ? 'var(--warn-2)' : 'var(--fg-4)' }}
                        >
                          {skipping === m.id ? 'Skipping…' : 'Skip'}
                        </button>
                      )}
                    </span>
                  )
                })}
                {missions.length > 3 && (
                  <button type="button" onClick={() => setAllMissions((v) => !v)} style={{ ...linkButton, paddingLeft: 20 }}>
                    {allMissions ? 'Show fewer' : `${missions.length - missionsShown.length} more`}
                  </button>
                )}
              </div>
            )}
          </Stage>
          <Stage
            index={3}
            current={stage}
            failed={failed}
            finished={finished}
            working={working}
            last
            title={STAGES[3].label}
            detail={
              finished
                ? `${scenarios.length} scenarios ready${scenariosStart ? ` · ${minutesBetween(scenariosStart, run.updated_at)} min` : ''}`
                : run.status === 'testing'
                  ? `${scenarios.length} of ${run.counts.tests_total} tried in the app`
                  : 'Up next'
            }
          />
        </aside>
        </div>
      </div>
    </div>
  )
}

const linkButton = { border: 'none', background: 'none', padding: 0, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12.5, color: 'var(--accent-2)', alignSelf: 'flex-start' } as const

function order(status: string) {
  return { running: 0, waiting: 0, done: 1, blocked: 1, failed: 1, skipped: 2, queued: 3 }[status] ?? 4
}

function missionMark(status: string) {
  if (status === 'running' || status === 'waiting') return '●'
  if (status === 'done') return '✓'
  if (status === 'queued') return '○'
  return '–'
}

function Stage({
  index,
  current,
  failed,
  finished,
  working,
  title,
  detail,
  last,
  children,
}: {
  index: number
  current: number
  failed: boolean
  finished: boolean
  working: boolean
  title: string
  detail: string
  last?: boolean
  children?: ReactNode
}) {
  const done = finished || (!failed && current > index) || (failed && current > index)
  const active = !finished && current === index
  return (
    <div style={{ display: 'flex', gap: 14 }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <span
          style={{
            width: 24,
            height: 24,
            flex: 'none',
            borderRadius: 1000,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxSizing: 'border-box',
            background: done ? 'var(--accent-2)' : active ? 'var(--accent-wash)' : 'white',
            border: `2px solid ${done || active ? 'var(--accent-2)' : 'var(--border-2)'}`,
            color: done ? 'white' : 'var(--accent-2)',
          }}
        >
          {done ? <FontAwesomeIcon icon={faCheck} style={{ fontSize: 10 }} /> : active && working ? <Spinner size={10} /> : active ? <span style={{ width: 8, height: 8, borderRadius: 1000, background: 'var(--accent-2)' }} /> : null}
        </span>
        {!last && <span style={{ width: 2, flex: 1, minHeight: 22, background: done ? 'var(--accent-2)' : 'var(--line)', transition: 'background 400ms ease' }} />}
      </div>
      <div style={{ paddingBottom: last ? 0 : 16, display: 'flex', flexDirection: 'column', gap: 3, flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: done || active ? 'var(--fg)' : 'var(--fg-5)' }}>{title}</span>
        {detail && <span style={{ fontSize: 12.5, color: active ? 'var(--fg-3)' : 'var(--fg-4)' }}>{detail}</span>}
        {children}
      </div>
    </div>
  )
}
