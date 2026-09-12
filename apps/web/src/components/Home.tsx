import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEllipsis, faLayerGroup, faPlus } from '@fortawesome/free-solid-svg-icons'
import { api, type ApplicationRead, type HomeApplicationRead, type UserRead } from '../api'
import { StatusPill } from './StatusPill'
import { Pagination } from './Pagination'
import { SkeletonRows } from './Skeleton'
import { Toast } from './Toast'
import { useEscapeToClose } from '../hooks/useEscapeToClose'

const POLL_INTERVAL_MS = 15000
const APPS_PER_PAGE = 8
// Mirrors MAX_ACTIVE_PROJECTS in apps/api/src/api/main.py — server enforces
// this for real. The old page-level "+ New Application" button used to
// disable itself with a tooltip at the cap; that button is gone now that
// "Add application" lives in AppShell's sidebar/topbar (shared across every
// screen, not just Home), so the cap is only enforced by ConnectAppForm's
// existing generic ApiError surfacing (a 409 at submit shows the server's
// message) rather than pre-emptively. Functionality preserved, just one step
// later.

export type ApplicationStage =
  | 'failed'
  | 'paused'
  | 'generating_tests'
  | 'suite_generated'
  | 'generating_scenarios'
  | 'scenarios_generated'
  | 'journeys_generated'
  | 'discovery_completed'
  | 'running'

// Single source of truth for "what is this application doing right now" —
// shared with Overview.tsx's Active pipelines widget so the two screens
// never disagree about which applications count as mid-pipeline.
export function applicationStage(application: HomeApplicationRead): {
  stage: ApplicationStage
  isRunning: boolean
  scenariosGenerating: boolean
  suiteGenerating: boolean
  testRunRunning: boolean
} {
  const discoveryStatus = application.discovery_status
  // `suite_count` alone can't tell "generation finished" from "generation
  // just started": EnsureTestSuiteActivity creates the TestSuite row before
  // its TestAssets do) — `suites_generating_count` is the suite.status-based
  // signal that fixes that: whether any suite is still actually mid-run.
  const suiteGenerating = application.suite_count > 0 && application.suites_generating_count > 0
  const scenariosGenerating =
    application.scenario_count > 0 && application.scenario_journeys_covered < application.journey_count
  const stage: ApplicationStage =
    discoveryStatus === 'failed' || discoveryStatus === 'paused'
      ? discoveryStatus
      : suiteGenerating
        ? 'generating_tests'
        : application.suite_count > 0
          ? 'suite_generated'
          : scenariosGenerating
            ? 'generating_scenarios'
            : application.scenario_count > 0
              ? 'scenarios_generated'
              : application.journey_count > 0
                ? 'journeys_generated'
                : discoveryStatus === 'complete' && application.discovery_stage === 'analyzed'
                  ? 'discovery_completed'
                  : 'running'
  return {
    stage,
    isRunning: discoveryStatus === 'running',
    scenariosGenerating,
    suiteGenerating,
    testRunRunning: application.last_test_run_status === 'running',
  }
}

function WarningIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3.5 21.5 20h-19L12 3.5Z" />
      <path d="M12 10v4" />
      <circle cx="12" cy="17.2" r="0.4" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(diffMs / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

// Same 90%/70% pass-rate cutoffs Workspace Overview's `_health_tier` uses
// (apps/api/src/api/main.py) — one health-tier vocabulary across the app.
function passRateColor(passRate: number): string {
  if (passRate >= 0.9) return 'var(--good-strong)'
  if (passRate >= 0.7) return 'var(--warn-strong)'
  return 'var(--danger-strong)'
}

function ApplicationRow({
  application,
  isAdmin,
  onResume,
  onChanged,
  onError,
}: {
  application: HomeApplicationRead
  isAdmin: boolean
  onResume: () => void
  onChanged: () => void
  onError: (message: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [nameDraft, setNameDraft] = useState(application.name)
  const [menuOpen, setMenuOpen] = useState(false)
  // Portaled to document.body and positioned from this rect — the table's
  // own rounded-corner container clips regular absolutely-positioned
  // children (see EXPERIENCE.md), which was hiding the menu for rows near
  // the bottom/edge of the table.
  const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  useEscapeToClose(() => confirmingDelete && !deleting && setConfirmingDelete(false))
  const skipBlurRef = useRef(false)

  const { stage, isRunning, scenariosGenerating, suiteGenerating, testRunRunning } = applicationStage(application)
  const testCasesComplete = application.suite_count > 0 && !suiteGenerating
  const hasJourneys = application.journey_count > 0
  const coveragePct = hasJourneys ? application.scenario_journeys_covered / application.journey_count : 0

  const deleteBlocked = isRunning || scenariosGenerating || suiteGenerating || testRunRunning
  const deleteBlockedReason = isRunning
    ? 'Discovery is still running'
    : scenariosGenerating
      ? 'Test case generation is still running'
      : suiteGenerating
        ? 'Test suite generation is still running'
        : testRunRunning
          ? 'A test run is still running'
          : undefined
  const passRate = application.last_test_run_pass_rate
  const hasCompletedRun = application.last_test_run_status === 'completed' && passRate != null
  const readyToExecute = stage === 'suite_generated' && !testRunRunning && !hasCompletedRun
  const displayStatus = testRunRunning
    ? 'test_run_running'
    : hasCompletedRun
      ? application.last_test_run_health.tier
      : readyToExecute
        ? 'ready_to_execute'
        : stage
  const activityLabel = application.last_test_run_created_at
    ? `Last run ${relativeTime(application.last_test_run_created_at)}`
    : `Updated ${relativeTime(application.created_at)}`
  const passRatePct = passRate == null ? null : Math.round(Math.min(1, Math.max(0, passRate)) * 100)

  function cancelRename() {
    skipBlurRef.current = true
    setNameDraft(application.name)
    setEditing(false)
  }

  async function saveRename() {
    skipBlurRef.current = true
    const trimmed = nameDraft.trim()
    if (!trimmed || trimmed === application.name) {
      cancelRename()
      return
    }
    setEditing(false)
    try {
      await api.renameApplication(application.id, trimmed)
      onChanged()
    } catch {
      setNameDraft(application.name)
      onError('Could not rename application — try again.')
    }
  }

  async function confirmDelete() {
    setDeleting(true)
    try {
      await api.deleteApplication(application.id)
      onChanged()
    } catch {
      onError('Could not delete application — try again.')
    } finally {
      setDeleting(false)
      setConfirmingDelete(false)
    }
  }

  const cellStyle: CSSProperties = { padding: '13px 11px', fontSize: 12.5 }

  return (
    <tr
      className="v2-table-row"
      style={{ cursor: 'pointer', borderBottom: '1px solid var(--row-line)' }}
      onClick={onResume}
    >
      <td style={{ ...cellStyle, padding: '13px 20px' }}>
        {editing ? (
          <input
            autoFocus
            value={nameDraft}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => setNameDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveRename()
              if (e.key === 'Escape') cancelRename()
            }}
            onBlur={() => {
              if (skipBlurRef.current) {
                skipBlurRef.current = false
                return
              }
              saveRename()
            }}
            style={{
              fontSize: 13.5,
              fontWeight: 500,
              border: '1px solid var(--border-2)',
              borderRadius: 6,
              padding: '3px 7px',
              width: '100%',
              maxWidth: 240,
              boxSizing: 'border-box',
              font: 'inherit',
            }}
          />
        ) : (
          <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-1)' }}>{application.name}</div>
        )}
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--fg-4)', marginTop: 3 }}>{application.url}</div>
      </td>
      <td
        style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--fg-3)' }}
        title={hasJourneys ? `${Math.round(coveragePct * 100)}% of journeys covered by scenarios` : undefined}
      >
        {application.journey_count}
      </td>
      <td style={{ ...cellStyle, textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--fg-1)' }}>
        {testCasesComplete ? application.test_case_count : '–'}
      </td>
      <td style={cellStyle}>
        {passRatePct == null ? (
          <span style={{ color: 'var(--fg-4)' }}>No runs yet</span>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ flex: 1, height: 4, borderRadius: 1000, background: 'var(--chip)', overflow: 'hidden', maxWidth: 120 }}>
              <div style={{ width: `${passRatePct}%`, height: '100%', background: passRateColor(passRatePct / 100) }} />
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--fg-2)', width: 36, textAlign: 'right' }}>
              {passRatePct}%
            </span>
          </div>
        )}
      </td>
      <td style={{ ...cellStyle, color: 'var(--fg-3)' }}>{activityLabel}</td>
      <td style={cellStyle}>
        <StatusPill
          status={displayStatus}
          pulsing={testRunRunning || isRunning || scenariosGenerating || suiteGenerating}
          dot={false}
        />
      </td>
      <td style={{ ...cellStyle, padding: '13px 16px', textAlign: 'right' }}>
        {isAdmin && !editing && (
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <button
              ref={menuButtonRef}
              type="button"
              title="More options"
              onClick={(e) => {
                e.stopPropagation()
                if (!menuOpen) {
                  const rect = menuButtonRef.current!.getBoundingClientRect()
                  setMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right })
                }
                setMenuOpen((v) => !v)
              }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 24,
                height: 24,
                borderRadius: 6,
                border: 'none',
                background: 'none',
                color: 'var(--fg-4)',
                padding: 0,
              }}
            >
              <FontAwesomeIcon icon={faEllipsis} style={{ fontSize: 17 }} />
            </button>
            {menuOpen &&
              menuPos &&
              createPortal(
                <>
                  <div
                    onClick={(e) => {
                      e.stopPropagation()
                      setMenuOpen(false)
                    }}
                    style={{ position: 'fixed', inset: 0, zIndex: 99 }}
                  />
                  <div
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      position: 'fixed',
                      top: menuPos.top,
                      right: menuPos.right,
                      minWidth: 140,
                      padding: 4,
                      zIndex: 100,
                      background: 'var(--panel)',
                      border: '1px solid var(--border-2)',
                      borderRadius: 10,
                      boxShadow: 'var(--panel-shadow)',
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        setMenuOpen(false)
                        setNameDraft(application.name)
                        setEditing(true)
                      }}
                      style={{ display: 'block', width: '100%', textAlign: 'left', padding: '9px 12px', fontSize: 13, border: 'none', background: 'none', color: 'var(--fg-1)', cursor: 'pointer', borderRadius: 6 }}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      disabled={deleteBlocked}
                      title={deleteBlockedReason}
                      onClick={(e) => {
                        e.stopPropagation()
                        setMenuOpen(false)
                        if (deleteBlocked) return
                        setConfirmingDelete(true)
                      }}
                      style={{
                        display: 'block',
                        width: '100%',
                        textAlign: 'left',
                        padding: '9px 12px',
                        fontSize: 13,
                        border: 'none',
                        background: 'none',
                        color: 'var(--bad)',
                        opacity: deleteBlocked ? 0.4 : 1,
                        cursor: deleteBlocked ? 'not-allowed' : 'pointer',
                        borderRadius: 6,
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </>,
                document.body,
              )}
          </div>
        )}
      </td>
      {confirmingDelete &&
        createPortal(
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Delete application"
            onClick={(e) => {
              e.stopPropagation()
              if (!deleting) setConfirmingDelete(false)
            }}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(15,23,42,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 24,
              zIndex: 100,
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{ maxWidth: 420, width: '100%', padding: 24, background: 'var(--panel)', borderRadius: 14, boxShadow: 'var(--panel-shadow)' }}
            >
              <div style={{ display: 'flex', gap: 14, marginBottom: 18 }}>
                <span
                  aria-hidden="true"
                  style={{
                    display: 'inline-flex',
                    width: 40,
                    height: 40,
                    borderRadius: 1000,
                    background: 'color-mix(in srgb, var(--bad) 12%, transparent)',
                    color: 'var(--bad)',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <WarningIcon size={19} />
                </span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 4, color: 'var(--fg)' }}>
                    Delete &ldquo;{application.name}&rdquo;?
                  </div>
                  <p style={{ margin: 0, lineHeight: 1.5, fontSize: 13, color: 'var(--fg-3)' }}>
                    This removes the application from your workspace. This can&apos;t be undone from here.
                  </p>
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button
                  type="button"
                  disabled={deleting}
                  onClick={(e) => {
                    e.stopPropagation()
                    setConfirmingDelete(false)
                  }}
                  style={{ padding: '9px 16px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--fg-2)', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={deleting}
                  onClick={(e) => {
                    e.stopPropagation()
                    confirmDelete()
                  }}
                  style={{
                    padding: '9px 16px',
                    borderRadius: 8,
                    border: 'none',
                    background: 'var(--bad)',
                    color: '#FFFFFF',
                    fontWeight: 600,
                    cursor: deleting ? 'default' : 'pointer',
                    opacity: deleting ? 0.7 : 1,
                  }}
                >
                  {deleting ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </tr>
  )
}

const COLUMN_HEADERS = ['Application', 'Journeys', 'Tests', 'Pass rate', 'Last activity', 'Status', '']

export function Home({
  user,
  onConnectApp,
  onResumeApplication,
}: {
  user: UserRead
  onConnectApp: () => void
  onResumeApplication: (application: ApplicationRead) => void
}) {
  const isAdmin = user.role === 'admin'
  const [applications, setApplications] = useState<HomeApplicationRead[] | null>(null)
  const [snackbar, setSnackbar] = useState<{ message: string; kind: 'error' | 'info' } | null>(null)
  const [page, setPage] = useState(0)

  useEffect(() => {
    if (!snackbar) return
    const timeout = setTimeout(() => setSnackbar(null), 3000)
    return () => clearTimeout(timeout)
  }, [snackbar])

  async function refreshApplications() {
    try {
      setApplications(await api.getHome())
    } catch {
      // best-effort — a transient failure just skips this refresh
    }
  }

  useEffect(() => {
    refreshApplications()
    const interval = setInterval(refreshApplications, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [])

  // Newest activity first — a project just connected and one that just ran
  // tests both count as "recent," so sort by whichever timestamp is later.
  const allApplications = (Array.isArray(applications) ? applications : []).toSorted((a, b) => {
    const activityTime = (app: HomeApplicationRead) =>
      Math.max(new Date(app.created_at).getTime(), app.last_test_run_created_at ? new Date(app.last_test_run_created_at).getTime() : 0)
    return activityTime(b) - activityTime(a)
  })
  const totalTestCases = allApplications.reduce((sum, a) => sum + a.test_case_count, 0)
  const totalPages = Math.max(1, Math.ceil(allApplications.length / APPS_PER_PAGE))
  const pageClamped = Math.min(page, totalPages - 1)
  const pagedApplications = allApplications.slice(pageClamped * APPS_PER_PAGE, pageClamped * APPS_PER_PAGE + APPS_PER_PAGE)

  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Applications</h1>
          <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4 }}>
            {allApplications.length} application{allApplications.length === 1 ? '' : 's'} onboarded · {totalTestCases} generated test cases
          </div>
        </div>
        <div style={{ flex: 1 }} />
      </div>

      {applications === null ? (
        <div style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 12, overflow: 'hidden', padding: 20 }}>
          <SkeletonRows count={6} height={38} gap={12} />
        </div>
      ) : applications.length > 0 ? (
        <div style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 12, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--panel-2)' }}>
                {COLUMN_HEADERS.map((h, i) => (
                  <th
                    key={h || i}
                    style={{
                      textAlign: i === 1 || i === 2 ? 'right' : 'left',
                      padding: i === 0 ? '11px 20px' : '11px',
                      fontSize: 10.5,
                      fontWeight: 600,
                      letterSpacing: '0.07em',
                      textTransform: 'uppercase',
                      color: 'var(--fg-4)',
                      borderBottom: '1px solid var(--border-2)',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pagedApplications.map((application) => (
                <ApplicationRow
                  key={application.id}
                  application={application}
                  isAdmin={isAdmin}
                  onResume={() => onResumeApplication(application)}
                  onChanged={refreshApplications}
                  onError={(message) => setSnackbar({ message, kind: 'error' })}
                />
              ))}
            </tbody>
          </table>
          <div style={{ padding: '11px 20px', background: 'var(--panel-2)' }}>
            <Pagination
              page={pageClamped}
              totalPages={totalPages}
              totalItems={allApplications.length}
              pageSize={APPS_PER_PAGE}
              onPrev={() => setPage(pageClamped - 1)}
              onNext={() => setPage(pageClamped + 1)}
              onPage={setPage}
            />
          </div>
        </div>
      ) : (
        <div
          style={{
            background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
            backdropFilter: 'blur(16px) saturate(1.25)',
            border: '1px solid var(--border-1)',
            borderRadius: 14,
            boxShadow: 'var(--panel-shadow)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            textAlign: 'center',
            padding: '58px 32px 52px',
          }}
        >
          <div style={{ position: 'relative', width: 230, height: 150, marginBottom: 30 }}>
            <div style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', width: 290, height: 290, borderRadius: 1000, background: 'var(--glow)' }} />
            <div style={{ position: 'absolute', left: '50%', top: 0, transform: 'translateX(-50%)', width: 186, borderRadius: 12, background: 'var(--panel-2)', border: '1px solid var(--border-2)', boxShadow: '0 18px 38px rgba(0,0,0,0.16)', overflow: 'hidden' }}>
              <div style={{ height: 26, background: 'var(--chip)', borderBottom: '1px solid var(--border-2)' }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '13px 14px 16px' }}>
                <div style={{ height: 6, width: 130, borderRadius: 1000, background: 'var(--chip)' }} />
                <div style={{ height: 6, width: 96, borderRadius: 1000, background: 'var(--chip)' }} />
                <div style={{ height: 6, width: 112, borderRadius: 1000, background: 'var(--chip)' }} />
              </div>
            </div>
            <div style={{ position: 'absolute', right: 2, bottom: 0, width: 62, height: 62, borderRadius: 1000, background: 'var(--panel-hi)', border: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 16px 32px rgba(0,0,0,0.22)' }}>
              <FontAwesomeIcon icon={faLayerGroup} style={{ fontSize: 22, color: "var(--accent-2)" }} />
            </div>
            <div style={{ position: 'absolute', left: 4, bottom: 14, width: 14, height: 14, borderRadius: 5, background: 'var(--chip)', border: '1px solid var(--border-2)', transform: 'rotate(-16deg)' }} />
          </div>
          <div style={{ fontSize: 19, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.015em' }}>Add your first application</div>
          <div style={{ fontSize: 13, color: 'var(--fg-3)', marginTop: 9, maxWidth: 460, lineHeight: '21px' }}>
            Point Vantage at a deployed URL and optional login. Discovery maps the pages, models journeys and generates the Playwright suite — usually inside 40 minutes.
          </div>
          <button
            type="button"
            onClick={onConnectApp}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              height: 38,
              padding: '0 20px',
              borderRadius: 8,
              background: 'var(--accent)',
              color: '#fff',
              fontSize: 13.5,
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: 'var(--accent-glow)',
              marginTop: 24,
              border: 'none',
            }}
          >
            <FontAwesomeIcon icon={faPlus} style={{ fontSize: 11 }} />
            Add application
          </button>
        </div>
      )}

      {snackbar && <Toast message={snackbar.message} kind={snackbar.kind} onDismiss={() => setSnackbar(null)} />}
    </div>
  )
}
