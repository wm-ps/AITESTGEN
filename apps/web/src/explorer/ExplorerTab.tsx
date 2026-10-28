import { useCallback, useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
  faArrowsRotate,
  faBell,
  faCompass,
  faEyeLowVision,
  faFileLines,
  faHourglassEnd,
  faHeartPulse,
  faLayerGroup,
  faPlay,
  faScaleBalanced,
  faStop,
  faPause,
  faUserCheck,
} from '@fortawesome/free-solid-svg-icons'
import { ApiError } from '../api'
import { AppIdentityLine } from '../components/AppIdentityLine'
import { LoadingDots, Spinner } from '../components/LoadingDots'
import {
  explorerApi,
  WORKING_STATUSES,
  type AppMap,
  type ExplorerEvent,
  type ExplorerHealthIssue,
  type ExplorerMission,
  type ExplorerQuestion,
  type ExplorerRun,
  type ExplorerTestCase,
} from './explorerApi'
import { HealthView } from './HealthView'
import { LiveView, type ExplorerView as View } from './LiveView'
import { ScenariosView } from './ScenariosView'
import { ScreensView } from './ScreensView'
import { SummaryView } from './SummaryView'
import { KnowledgePanel, QuestionsDialog } from './QuestionsView'
import { RolesPanel } from './RolesPanel'
import { glassCard, IconTile, Lightbox } from './ui'

const EVENT_POLL_MS = 1500
const RUN_POLL_MS = 2500

export function ExplorerTab({
  applicationId,
  applicationName,
  applicationUrl,
  onGenerateTests,
}: {
  applicationId: string
  applicationName: string
  applicationUrl: string
  onGenerateTests?: () => Promise<void>
}) {
  const [run, setRun] = useState<ExplorerRun | null | undefined>(undefined)
  const [events, setEvents] = useState<ExplorerEvent[]>([])
  const [issues, setIssues] = useState<ExplorerHealthIssue[]>([])
  const [appMap, setAppMap] = useState<AppMap | null>(null)
  const [missions, setMissions] = useState<ExplorerMission[]>([])
  const [tests, setTests] = useState<ExplorerTestCase[]>([])
  const [questions, setQuestions] = useState<ExplorerQuestion[] | null>(null)
  const [view, setView] = useState<View>('live')
  const [questionsOpen, setQuestionsOpen] = useState(false)
  const [lightbox, setLightbox] = useState<{ shotId: string; caption: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [pausing, setPausing] = useState<'pause' | 'resume' | null>(null)
  const [startingFresh, setStartingFresh] = useState(false)
  const cursor = useRef(0)

  const working = run ? WORKING_STATUSES.includes(run.status) : false

  // Load the latest run for this app on open.
  useEffect(() => {
    let cancelled = false
    setRun(undefined)
    setEvents([])
    cursor.current = 0
    explorerApi
      .latestRun(applicationId)
      .then((r) => {
        if (cancelled) return
        setRun(r)
        if (r?.status === 'awaiting_confirmation') setView('summary')
      })
      .catch(() => !cancelled && setRun(null))
    return () => {
      cancelled = true
    }
  }, [applicationId])

  const pullEvents = useCallback(async (runId: string) => {
    // The API pages (200 at a time): keep reading until caught up, or a
    // finished run shows only its first stages.
    for (;;) {
      const fresh = await explorerApi.events(runId, cursor.current)
      if (!fresh.length) break
      cursor.current = fresh[fresh.length - 1].id
      setEvents((prev) => [...prev, ...fresh])
      if (fresh.length < 200) break
    }
  }, [])

  // Feed: fast while working, one fetch otherwise.
  useEffect(() => {
    if (!run) return
    void pullEvents(run.id)
    if (!working) return
    const t = setInterval(() => void pullEvents(run.id).catch(() => {}), EVENT_POLL_MS)
    return () => clearInterval(t)
  }, [run?.id, working, pullEvents]) // eslint-disable-line react-hooks/exhaustive-deps

  // Run status while working.
  useEffect(() => {
    if (!run || !working) return
    const t = setInterval(() => {
      explorerApi
        .getRun(run.id)
        .then((r) => {
          setRun((prev) => {
            if (r.status === 'awaiting_confirmation' && prev?.status !== 'awaiting_confirmation') setView('summary')
            return r
          })
        })
        .catch(() => {})
    }, RUN_POLL_MS)
    return () => clearInterval(t)
  }, [run?.id, working]) // eslint-disable-line react-hooks/exhaustive-deps

  // Possible bugs refresh whenever their count moves.
  useEffect(() => {
    if (!run) return
    explorerApi.health(run.id).then(setIssues).catch(() => {})
  }, [run?.id, run?.counts.health_issues, run?.health_score]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!run) return
    explorerApi.questions(run.id).then(setQuestions).catch(() => {})
  }, [run?.id, run?.counts.questions_open, run?.status]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!run) return
    explorerApi.map(run.id).then(setAppMap).catch(() => {})
  }, [run?.id, run?.counts.screens, run?.counts.hidden_screens]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!run) return
    explorerApi.missions(run.id).then(setMissions).catch(() => {})
  }, [run?.id, run?.counts.missions_total, run?.counts.missions_done, run?.counts.missions_running]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!run) return
    explorerApi.tests(run.id).then(setTests).catch(() => {})
  }, [run?.id, run?.counts.tests_total, run?.counts.tests_proven, run?.counts.tests_known_bugs, run?.counts.tests_building]) // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    setStarting(true)
    setError(null)
    try {
      const r = await explorerApi.startRun(applicationId)
      cursor.current = 0
      setEvents([])
      setIssues([])
      setAppMap(null)
      setMissions([])
      setTests([])
      setQuestions(null)
      setRun(r)
      setView('live')
      setStartingFresh(false)
    } catch (e) {
      setError(
        e instanceof ApiError && e.message === 'EXPLORER_UNAVAILABLE'
          ? 'Explorer is not available right now — its background service is not running.'
          : e instanceof Error
            ? e.message
            : 'Could not start Explorer.',
      )
    } finally {
      setStarting(false)
    }
  }

  const stop = async () => {
    if (!run) return
    setStopping(true)
    try {
      setRun(await explorerApi.stop(run.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not stop Explorer.')
    } finally {
      setStopping(false)
    }
  }

  // Pause halts the run; Resume carries it on from the step it reached
  // (also after a server problem), keeping everything already done.
  const pauseOrResume = async (action: 'pause' | 'resume') => {
    if (!run) return
    setPausing(action)
    try {
      setRun(await explorerApi[action](run.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not ${action} Explorer.`)
    } finally {
      setPausing(null)
    }
  }
  const resumable = run?.status === 'paused' || run?.status === 'stopped' || run?.status === 'failed'

  const openShot = (shotId: string, caption: string) => setLightbox({ shotId, caption })
  // An answer can turn a possible bug into a confirmed one (or drop it), so
  // the bug list reloads with the questions.
  const refreshAfterAnswer = async () => {
    if (!run) return
    const [q, r, h] = await Promise.all([explorerApi.questions(run.id), explorerApi.getRun(run.id), explorerApi.health(run.id)])
    setQuestions(q)
    setRun(r)
    setIssues(h)
  }
  // "Is this a bug?" questions never hold Explorer up; they live with the bugs.
  const needsYou = run?.status === 'awaiting_confirmation' || (questions ?? []).some((q) => q.status === 'open' && q.kind !== 'rule')

  return (
    <div style={{ width: '100%', maxWidth: 'var(--content-max-wide)', margin: '0 auto', boxSizing: 'border-box' }}>
      <style>
        {'@keyframes explorer-scan { 0% { background-position: 0 -40%; } 100% { background-position: 0 140%; } }' +
          // Anything waiting on the person pulses, so it is never missed.
          '@keyframes explorer-attention { 0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--warn-2) 45%, transparent); } 70% { box-shadow: 0 0 0 12px transparent; } 100% { box-shadow: 0 0 0 0 transparent; } }'}
      </style>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 'var(--space-8)', marginBottom: 'var(--space-7)', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h2 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Explorer</h2>
          </div>
          <AppIdentityLine name={applicationName} url={applicationUrl} />
          {run && (
            <div className="caption" style={{ fontSize: 13, marginTop: 3, display: 'flex', alignItems: 'center', gap: 8 }}>
              {working && <span style={{ width: 7, height: 7, borderRadius: 1000, background: 'var(--accent-2)', animation: 'v2-pulse 1.4s ease-in-out infinite' }} />}
              {run.headline}
            </div>
          )}
        </div>
        {run && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {(() => {
              const open = (questions ?? []).filter((q) => q.status === 'open').length
              const waiting = needsYou && run.status !== 'awaiting_confirmation'
              return (
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => setQuestionsOpen(true)}
                  aria-label={open ? `Questions, ${open} open` : 'Questions'}
                  title={waiting ? 'Explorer is waiting on your answer' : 'Questions Explorer asked you'}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 7, position: 'relative', animation: waiting ? 'explorer-attention 1.6s ease-out infinite' : undefined }}
                >
                  <FontAwesomeIcon icon={faBell} style={{ fontSize: 11, color: waiting ? 'var(--warn-2)' : undefined }} /> Questions
                  {open > 0 && (
                    <span style={{ fontSize: 11, fontWeight: 700, lineHeight: '17px', minWidth: 18, textAlign: 'center', padding: '0 6px', borderRadius: 1000, color: 'white', background: waiting ? 'var(--warn-2)' : 'var(--accent-2)' }}>{open}</span>
                  )}
                </button>
              )
            })()}
            {working && (
              <button type="button" className="button-secondary" onClick={() => pauseOrResume('pause')} disabled={pausing !== null || stopping} title="Halt now and carry on later from this point" style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                {pausing === 'pause' ? <LoadingDots label="Pausing" /> : (<><FontAwesomeIcon icon={faPause} style={{ fontSize: 11 }} /> Pause</>)}
              </button>
            )}
            {resumable && (
              <button type="button" className="button-primary" onClick={() => pauseOrResume('resume')} disabled={pausing !== null} title="Carry on from where this run stopped; nothing finished is redone" style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                {pausing === 'resume' ? <LoadingDots label="Resuming" /> : (<><FontAwesomeIcon icon={faPlay} style={{ fontSize: 11 }} /> Resume</>)}
              </button>
            )}
            {working ? (
              <button type="button" className="button-secondary" onClick={stop} disabled={stopping} style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                {stopping ? <LoadingDots label="Stopping" /> : (<><FontAwesomeIcon icon={faStop} style={{ fontSize: 11 }} /> Stop</>)}
              </button>
            ) : (
              <button type="button" className="button-secondary" onClick={() => setStartingFresh(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                <FontAwesomeIcon icon={faArrowsRotate} style={{ fontSize: 11 }} /> New run
              </button>
            )}
          </div>
        )}
      </div>

      {error && (
        <p className="caption" role="alert" style={{ color: 'var(--danger)', marginTop: 0 }}>
          {error}
        </p>
      )}

      {run === undefined ? (
        <div style={{ ...glassCard, padding: 28, display: 'flex', gap: 10, alignItems: 'center', color: 'var(--fg-3)', fontSize: 13.5 }}>
          <Spinner size={14} /> Loading Explorer…
        </div>
      ) : run === null || startingFresh ? (
        <StartCard applicationId={applicationId} applicationName={applicationName} busy={starting} onStart={start} onCancel={run ? () => setStartingFresh(false) : undefined} />
      ) : (
        <>
          {run.status === 'expired' && (
            // Over for good: no Resume, no Confirm. A new run starts from what this one learned.
            <div role="status" style={{ ...glassCard, padding: '14px 18px', marginBottom: 16, display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', borderColor: 'color-mix(in srgb, var(--warn-2) 35%, transparent)' }}>
              <FontAwesomeIcon icon={faHourglassEnd} style={{ fontSize: 16, color: 'var(--warn-2)' }} />
              <div style={{ flex: '1 1 320px', fontSize: 13, color: 'var(--fg-2)', lineHeight: '19px' }}>
                <strong style={{ color: 'var(--fg)' }}>This App Summary expired.</strong> Nobody confirmed it within 14 days, so this run has ended and can't be resumed. Start a new run: it begins from the screens this one already learned, and your answers are kept.
              </div>
              <button type="button" className="button-primary" onClick={() => setStartingFresh(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                <FontAwesomeIcon icon={faArrowsRotate} style={{ fontSize: 11 }} /> Start a new run
              </button>
            </div>
          )}
          {resumable && (
            <div style={{ ...glassCard, padding: '12px 16px', marginBottom: 16, fontSize: 13, color: 'var(--fg-2)', borderColor: run.status === 'failed' ? 'color-mix(in srgb, var(--bad) 30%, transparent)' : undefined }}>
              <strong style={{ color: run.status === 'failed' ? 'var(--bad)' : 'var(--fg)' }}>
                {run.status === 'failed' ? 'This run did not finish.' : run.status === 'paused' ? 'This run is paused.' : 'This run was stopped.'}
              </strong>{' '}
              {run.error ? `Reason: ${run.error}. ` : ''}Press Resume to carry on from where it stopped. Everything already done is kept.
            </div>
          )}
          <Tabs
            view={view}
            onChange={setView}
            items={[
              { key: 'live', label: 'Live', badge: working ? 'live' : undefined },
              { key: 'summary', label: 'What it learned', badge: run.status === 'awaiting_confirmation' ? 'review' : undefined },
              { key: 'screens', label: 'Screens', count: run.counts.screens },
              { key: 'scenarios', label: 'Scenarios', count: run.counts.tests_proven + run.counts.tests_known_bugs },
            ]}
          />
          <div key={view} style={{ animation: 'aitg-fade-up 240ms ease' }}>
            {view === 'live' && (
              <LiveView
                run={run}
                events={events}
                questions={questions}
                missions={missions}
                tests={tests}
                screens={appMap?.screens ?? []}
                applicationUrl={applicationUrl}
                onOpenShot={openShot}
                onGoTo={(v) => (v === 'questions' ? setQuestionsOpen(true) : setView(v))}
                onSkipMission={async (missionId) => {
                  await explorerApi.skipMission(missionId)
                  setMissions(await explorerApi.missions(run.id))
                  void pullEvents(run.id)
                }}
              />
            )}
            {view === 'screens' && <ScreensView map={appMap} issues={issues} onOpenShot={openShot} />}
            {view === 'scenarios' && <ScenariosView run={run} tests={tests} screens={appMap?.screens ?? []} onOpenShot={openShot} onGenerateTests={onGenerateTests} onVerdict={async (testId, verdict) => {
              setRun(await explorerApi.verdict(testId, verdict))
              setTests(await explorerApi.tests(run.id))
            }} />}
            {view === 'summary' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <SummaryView
                  run={run}
                  screens={appMap?.screens ?? []}
                  onSave={async (brief) => setRun(await explorerApi.saveBrief(run.id, brief))}
                  onConfirm={async () => {
                    setRun(await explorerApi.confirm(run.id))
                    void pullEvents(run.id)
                  }}
                />
                <KnowledgePanel applicationId={applicationId} />
                {/* Last and folded: worth a look, never the headline. */}
                <HealthView issues={issues} screens={appMap?.screens ?? []} questions={questions ?? []} onAnswered={refreshAfterAnswer} onOpenShot={openShot} />
              </div>
            )}
          </div>
        </>
      )}
      {questionsOpen && <QuestionsDialog questions={questions} onAnswered={refreshAfterAnswer} onOpenShot={openShot} onClose={() => setQuestionsOpen(false)} />}
      {lightbox && <Lightbox shotId={lightbox.shotId} caption={lightbox.caption} onClose={() => setLightbox(null)} />}
    </div>
  )
}

// Plain underline tabs: text only, the active one carries an accent
// underline, counts are quiet grey numbers. Arrow keys move between tabs.
// Only a tab that needs you (or is live) gets a dot.
function Tabs({ view, onChange, items }: { view: View; onChange: (v: View) => void; items: { key: View; label: string; count?: number; badge?: 'live' | 'review' }[] }) {
  const move = (from: number, step: number) => {
    const next = items[(from + step + items.length) % items.length]
    onChange(next.key)
    document.getElementById(`explorer-tab-${next.key}`)?.focus()
  }
  return (
    <div role="tablist" aria-label="Explorer" style={{ display: 'flex', gap: 28, marginBottom: 20, borderBottom: '1px solid var(--line)', overflowX: 'auto' }}>
      <style>{'.explorer-tab:hover{color:var(--fg)!important}.explorer-tab:focus-visible{outline:2px solid var(--accent-2);outline-offset:2px;border-radius:4px}'}</style>
      {items.map((item, i) => {
        const active = item.key === view
        return (
          <button
            key={item.key}
            id={`explorer-tab-${item.key}`}
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            type="button"
            className="explorer-tab"
            onClick={() => onChange(item.key)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowRight') move(i, 1)
              if (e.key === 'ArrowLeft') move(i, -1)
            }}
            style={{
              flex: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 7,
              height: 40,
              padding: 0,
              marginBottom: -1,
              border: 'none',
              borderBottom: `2px solid ${active ? 'var(--accent-2)' : 'transparent'}`,
              background: 'transparent',
              fontFamily: 'inherit',
              fontSize: 14,
              fontWeight: active ? 600 : 500,
              color: active ? 'var(--fg)' : 'var(--fg-4)',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'color 150ms ease, border-color 150ms ease',
            }}
          >
            <span>{item.label}</span>
            {item.count !== undefined && <span style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg-5)' }}>{item.count}</span>}
            {item.badge === 'live' && <span aria-label="Live" style={{ width: 7, height: 7, flex: 'none', borderRadius: 1000, background: 'var(--bad)', animation: 'v2-pulse 1.4s ease-in-out infinite' }} />}
            {item.badge === 'review' && <span aria-label="Needs you" style={{ width: 8, height: 8, flex: 'none', borderRadius: 1000, background: 'var(--warn-2)', animation: 'explorer-attention 1.6s ease-out infinite' }} />}
          </button>
        )
      })}
    </div>
  )
}

function StartCard({ applicationId, applicationName, busy, onStart, onCancel }: { applicationId: string; applicationName: string; busy: boolean; onStart: () => void; onCancel?: () => void }) {
  const steps = [
    { icon: faUserCheck, title: 'Signs in and looks around', body: 'Uses the saved login, then reads each screen the way a person would.' },
    { icon: faLayerGroup, title: 'Understands, not just clicks', body: 'Names screens by what they mean — a thousand customer pages count as one.' },
    { icon: faEyeLowVision, title: 'Spots hidden parts', body: 'Notes sections that probably only appear for certain choices, amounts or users.' },
    { icon: faHeartPulse, title: 'Checks app health', body: 'Flags broken screens, server errors, slow pages and wording mistakes.' },
    { icon: faScaleBalanced, title: "Doesn't trust the app blindly", body: 'Judges what it sees against common sense and what you tell it.' },
    { icon: faFileLines, title: 'Writes an App Summary', body: 'A one-page summary of the business for you to correct and confirm.' },
  ]
  return (
    <div style={{ ...glassCard, padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '26px 28px', display: 'flex', gap: 18, alignItems: 'flex-start', background: 'linear-gradient(135deg, rgba(255,255,255,0.96), color-mix(in srgb, var(--accent-wash) 75%, white))', borderBottom: '1px solid var(--line)' }}>
        <span style={{ position: 'relative', flex: 'none' }}>
          <IconTile icon={faCompass} size={48} />
          <span aria-hidden style={{ position: 'absolute', inset: 0, borderRadius: 9, border: '2px solid var(--accent-2)', animation: 'v2-ring 2.2s ease-out infinite' }} />
        </span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 650, color: 'var(--fg)', letterSpacing: '-0.01em' }}>Let Explorer get to know {applicationName}</h3>
          <p style={{ margin: 0, fontSize: 13.5, color: 'var(--fg-3)', lineHeight: '20px', maxWidth: 760 }}>
            Like a sharp new QA engineer on day one: it studies the app first, tells you what it understood and how healthy the app looks, and waits for you to confirm before going further. Your current Journeys are not affected.
          </p>
        </div>
      </div>
      <div style={{ padding: '20px 28px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
        {steps.map((s, i) => (
          <div key={s.title} style={{ display: 'flex', gap: 12, animation: `aitg-fade-up 360ms ease ${i * 50}ms both` }}>
            <IconTile icon={s.icon} tone="neutral" size={34} />
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>{s.title}</div>
              <div style={{ fontSize: 12.5, color: 'var(--fg-3)', lineHeight: '18px' }}>{s.body}</div>
            </div>
          </div>
        ))}
      </div>
      <div style={{ padding: '0 28px 24px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <RolesPanel applicationId={applicationId} />
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 6 }}>
          {onCancel && (
            <button type="button" className="button-secondary" onClick={onCancel}>
              Cancel
            </button>
          )}
          <button type="button" className="button-primary" disabled={busy} onClick={onStart} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {busy ? <LoadingDots label="Starting" /> : (<><FontAwesomeIcon icon={faPlay} style={{ fontSize: 11 }} /> Start exploring</>)}
          </button>
        </div>
      </div>
    </div>
  )
}
