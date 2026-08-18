import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { api, type ApplicationRead, type HomeApplicationRead, type UserRead } from '../api'
import { StatusPill } from './StatusPill'
import { Pagination } from './Pagination'

const POLL_INTERVAL_MS = 15000
const APPS_PER_PAGE = 5
// Mirrors MAX_ACTIVE_PROJECTS in apps/api/src/api/main.py — server enforces
// this for real, this just keeps the button from inviting a 409.
const MAX_ACTIVE_PROJECTS = 4

function FolderIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3.5 7.2A1.7 1.7 0 0 1 5.2 5.5h3.4l1.7 1.7h8a1.7 1.7 0 0 1 1.7 1.7v8.4a1.7 1.7 0 0 1-1.7 1.7H5.2a1.7 1.7 0 0 1-1.7-1.7V7.2Z" />
    </svg>
  )
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

function MoreIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="5" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="12" cy="19" r="1.8" />
    </svg>
  )
}

function ApplicationCard({
  application,
  isAdmin,
  onResume,
  onBlocked,
  onChanged,
  onError,
}: {
  application: HomeApplicationRead
  isAdmin: boolean
  onResume: () => void
  onBlocked: () => void
  onChanged: () => void
  onError: (message: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [nameDraft, setNameDraft] = useState(application.name)
  const [menuOpen, setMenuOpen] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const skipBlurRef = useRef(false)

  const discoveryStatus = application.discovery_status
  // `suite_count` alone can't tell "generation finished" from "generation
  // just started": EnsureTestSuiteActivity creates the TestSuite row before
  // its TestAssets exist. A count-based check here (test_case_count <
  // scenario_count) never recovers once a Scenario is permanently skipped
  // or fails all its wave retries — same gap TestSuiteResults.tsx's
  // isComplete had. `suites_generating_count` is the suite.status-based
  // signal that fix uses: whether any suite is still actually mid-run.
  const suiteGenerating = application.suite_count > 0 && application.suites_generating_count > 0
  const testCasesComplete = application.suite_count > 0 && !suiteGenerating
  const stage =
    discoveryStatus === 'failed' || discoveryStatus === 'paused'
      ? discoveryStatus
      : suiteGenerating
        ? 'generating_tests'
        : application.suite_count > 0
          ? 'suite_generated'
          : application.scenario_count > 0
            ? 'scenarios_generated'
            : application.journey_count > 0
              ? 'journeys_generated'
              : discoveryStatus === 'complete'
                ? 'discovery_completed'
                : 'running'

  const isRunning = discoveryStatus === 'running'

  const kebabButtonStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 24,
    height: 24,
    borderRadius: 6,
    border: 'none',
    background: 'none',
    color: 'var(--ink-muted)',
    padding: 0,
    flexShrink: 0,
  }

  const menuItemStyle: CSSProperties = {
    display: 'block',
    width: '100%',
    textAlign: 'left',
    padding: '9px 14px',
    fontSize: 13.5,
    fontWeight: 500,
    border: 'none',
    background: 'none',
    color: 'var(--ink)',
    cursor: 'pointer',
  }

  const renameActionButtonStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 24,
    height: 24,
    borderRadius: 6,
    border: 'none',
    background: 'none',
    padding: 0,
    fontSize: 14,
    lineHeight: 1,
    cursor: 'pointer',
    flexShrink: 0,
  }

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
      onError('Could not rename project — try again.')
    }
  }

  async function confirmDelete() {
    setDeleting(true)
    try {
      await api.deleteApplication(application.id)
      onChanged()
    } catch {
      onError('Could not delete project — try again.')
    } finally {
      setDeleting(false)
      setConfirmingDelete(false)
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={isRunning ? onBlocked : onResume}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') (isRunning ? onBlocked : onResume)()
      }}
      className="card-panel home-app-card"
      style={{
        textAlign: 'left',
        borderColor: 'var(--border-hairline)',
        padding: '20px 22px',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        maxWidth: 360,
        width: '100%',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 'var(--space-5)',
          marginBottom: 'var(--space-7)',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            display: 'inline-flex',
            width: 42,
            height: 42,
            borderRadius: 10,
            background: 'var(--accent-wash)',
            color: 'var(--accent)',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <FolderIcon size={19} />
        </span>
        <StatusPill status={stage} pulsing={isRunning || suiteGenerating} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-4)', marginBottom: 'var(--space-5)' }}>
        {editing ? (
          <>
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
                fontSize: 15,
                fontWeight: 700,
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '2px 6px',
                flex: 1,
                minWidth: 0,
                boxSizing: 'border-box',
                font: 'inherit',
              }}
            />
            <button
              type="button"
              title="Save"
              onClick={(e) => {
                e.stopPropagation()
                saveRename()
              }}
              style={{ ...renameActionButtonStyle, color: 'var(--accent)' }}
            >
              ✓
            </button>
            <button
              type="button"
              title="Cancel"
              onClick={(e) => {
                e.stopPropagation()
                cancelRename()
              }}
              style={{ ...renameActionButtonStyle, color: 'var(--ink-muted)' }}
            >
              ✕
            </button>
          </>
        ) : (
          <div
            style={{
              fontSize: 15,
              fontWeight: 700,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              minWidth: 0,
              maxWidth: 'calc(100% - 28px)',
            }}
          >
            {application.name}
          </div>
        )}
        {isAdmin && !editing && (
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <button
              type="button"
              title="More options"
              onClick={(e) => {
                e.stopPropagation()
                setMenuOpen((v) => !v)
              }}
              style={kebabButtonStyle}
            >
              <MoreIcon size={16} />
            </button>
            {menuOpen && (
              <>
                <div
                  onClick={(e) => {
                    e.stopPropagation()
                    setMenuOpen(false)
                  }}
                  style={{ position: 'fixed', inset: 0, zIndex: 9 }}
                />
                <div
                  onClick={(e) => e.stopPropagation()}
                  className="card-panel"
                  style={{
                    position: 'absolute',
                    top: '100%',
                    right: 0,
                    marginTop: 4,
                    minWidth: 140,
                    padding: 4,
                    zIndex: 10,
                    boxShadow: 'var(--shadow-dropdown-lg)',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false)
                      setNameDraft(application.name)
                      setEditing(true)
                    }}
                    style={menuItemStyle}
                  >
                    Rename
                  </button>
                  <button
                    type="button"
                    disabled={isRunning}
                    title={isRunning ? 'Discovery is still running' : undefined}
                    onClick={(e) => {
                      e.stopPropagation()
                      setMenuOpen(false)
                      setConfirmingDelete(true)
                    }}
                    style={{
                      ...menuItemStyle,
                      color: 'var(--danger)',
                      opacity: isRunning ? 0.4 : 1,
                      cursor: isRunning ? 'not-allowed' : 'pointer',
                    }}
                  >
                    Delete
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-4)' }}>
        <span>
          <span style={{ fontSize: 15, fontWeight: 700 }}>{application.journey_count}</span>{' '}
          <span className="caption" style={{ fontSize: 12 }}>
            journeys
          </span>
        </span>
        {testCasesComplete && (
          <>
            <span aria-hidden="true" style={{ width: 1, height: 12, background: 'var(--border)' }} />
            <span>
              <span style={{ fontSize: 15, fontWeight: 700 }}>{application.test_case_count}</span>{' '}
              <span className="caption" style={{ fontSize: 12 }}>
                test cases
              </span>
            </span>
          </>
        )}
      </div>
      {confirmingDelete && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Delete project"
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
            padding: 'var(--space-9)',
            zIndex: 100,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="card-panel"
            style={{ maxWidth: 420, width: '100%', padding: 'var(--space-8)' }}
          >
            <div style={{ display: 'flex', gap: 'var(--space-6)', marginBottom: 'var(--space-7)' }}>
              <span
                aria-hidden="true"
                style={{
                  display: 'inline-flex',
                  width: 40,
                  height: 40,
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--danger-wash)',
                  color: 'var(--danger)',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <WarningIcon size={19} />
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 4 }}>
                  Delete &ldquo;{application.name}&rdquo;?
                </div>
                <p className="caption" style={{ margin: 0, lineHeight: 1.5 }}>
                  This removes the project from your workspace. This can&apos;t be undone from here.
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-4)' }}>
              <button
                type="button"
                className="button-secondary"
                disabled={deleting}
                onClick={(e) => {
                  e.stopPropagation()
                  setConfirmingDelete(false)
                }}
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
                  borderRadius: 'var(--radius)',
                  border: 'none',
                  background: 'var(--danger)',
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
    </div>
  )
}

export function Home({
  user,
  onConnectApp,
  onResumeApplication,
}: {
  user: UserRead
  onConnectApp: () => void
  onResumeApplication: (application: ApplicationRead) => void
}) {
  const firstName = user.name.trim().split(/\s+/)[0]
  const isAdmin = user.role === 'admin'
  const [showDemo, setShowDemo] = useState(false)
  const [applications, setApplications] = useState<HomeApplicationRead[] | null>(null)
  const [snackbar, setSnackbar] = useState<string | null>(null)
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

  const applicationList = Array.isArray(applications) ? applications : []
  const totalPages = Math.max(1, Math.ceil(applicationList.length / APPS_PER_PAGE))
  const pageClamped = Math.min(page, totalPages - 1)
  const pagedApplications = applicationList.slice(
    pageClamped * APPS_PER_PAGE,
    pageClamped * APPS_PER_PAGE + APPS_PER_PAGE,
  )

  return (
    <main
      style={{
        width: '100%',
        boxSizing: 'border-box',
        height: 'calc(100vh - 64px)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        background:
          'radial-gradient(900px 500px at 85% -10%, var(--accent-wash-soft) 0%, transparent 55%), linear-gradient(180deg, #FBFCFE 0%, #F6F9FB 100%)',
      }}
    >
      <div
        style={{
          flex: 1,
          minWidth: 0,
          overflow: 'hidden',
          padding: '36px 44px',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-9)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 'var(--space-8)',
            flexShrink: 0,
            animation: 'aitg-fade-up 0.4s ease-out both',
          }}
        >
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>
              Welcome, {firstName}
            </div>
            <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.02em', margin: 0 }}>Projects</h1>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)', flexShrink: 0 }}>
            <button
              type="button"
              className="button-secondary"
              onClick={() => setShowDemo(true)}
              style={{ padding: '11px 18px' }}
            >
              Watch Demo
            </button>
            {applications && applications.length > 0 && (
              <button
                type="button"
                className="button-primary"
                disabled={applications.length >= MAX_ACTIVE_PROJECTS}
                title={
                  applications.length >= MAX_ACTIVE_PROJECTS
                    ? `Maximum of ${MAX_ACTIVE_PROJECTS} active projects reached — delete one before adding another.`
                    : undefined
                }
                onClick={onConnectApp}
                style={{
                  padding: '11px 18px',
                  opacity: applications.length >= MAX_ACTIVE_PROJECTS ? 0.5 : 1,
                  cursor: applications.length >= MAX_ACTIVE_PROJECTS ? 'not-allowed' : 'pointer',
                }}
              >
                + New Project
              </button>
            )}
          </div>
        </div>

        {applications === null ? null : applications.length > 0 ? (
          <>
            <div
              style={{
                flex: 1,
                minHeight: 0,
                overflowY: 'auto',
                display: 'flex',
                flexWrap: 'wrap',
                alignContent: 'flex-start',
                gap: 'var(--space-6)',
                animation: 'aitg-fade-up 0.4s ease-out 0.1s both',
              }}
            >
              {pagedApplications.map((application) => (
                <ApplicationCard
                  key={application.id}
                  application={application}
                  isAdmin={isAdmin}
                  onResume={() => onResumeApplication(application)}
                  onBlocked={() => setSnackbar('Please wait while the discovery process completes.')}
                  onChanged={refreshApplications}
                  onError={setSnackbar}
                />
              ))}
            </div>
            <Pagination
              page={pageClamped}
              totalPages={totalPages}
              onPrev={() => setPage(pageClamped - 1)}
              onNext={() => setPage(pageClamped + 1)}
            />
          </>
        ) : (
          <div
            style={{
              border: '1px dashed var(--border)',
              borderRadius: 'var(--radius-xl)',
              boxSizing: 'border-box',
              padding: 'var(--space-10)',
              flex: 1,
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              animation: 'aitg-fade-up 0.4s ease-out 0.05s both',
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: 'inline-flex',
                width: 52,
                height: 52,
                borderRadius: 'var(--radius-full)',
                background: 'var(--accent-wash)',
                color: 'var(--accent)',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 'var(--space-8)',
                flexShrink: 0,
              }}
            >
              <FolderIcon size={24} />
            </span>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 'var(--space-3)' }}>No projects yet</div>
            <p className="caption" style={{ fontSize: 14, margin: '0 0 var(--space-8)', maxWidth: 420, lineHeight: 1.5 }}>
              Connect your first application to start discovering journeys and generating tests — no
              scripts required.
            </p>
            <button type="button" className="button-primary" onClick={onConnectApp} style={{ padding: '10px 20px' }}>
              + Create New Project
            </button>
          </div>
        )}
      </div>

      {showDemo && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Product demo"
          onClick={() => setShowDemo(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 'var(--space-9)',
            zIndex: 50,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="card-panel"
            style={{ maxWidth: 560, width: '100%', padding: 'var(--space-8)' }}
          >
            <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 4 }}>Product demo</div>
            <p className="caption" style={{ margin: '0 0 var(--space-7)' }}>
              Connect App → Discover Journeys → Review Scenarios → Generate Suite, in a few minutes.
            </p>
            <video
              controls
              autoPlay
              src="/demo/app-demo.mp4"
              style={{
                width: '100%',
                aspectRatio: '16 / 9',
                borderRadius: 'var(--radius-lg)',
                marginBottom: 'var(--space-7)',
                background: 'var(--ink)',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button type="button" className="button-secondary" onClick={() => setShowDemo(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {snackbar && (
        <div
          role="status"
          style={{
            position: 'fixed',
            right: 'var(--space-9)',
            bottom: 'var(--space-9)',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-4)',
            background: 'var(--ink)',
            color: '#FFFFFF',
            padding: '12px 18px',
            borderRadius: 'var(--radius)',
            fontSize: 13.5,
            boxShadow: '0 12px 28px rgba(15,23,42,0.25)',
            zIndex: 60,
          }}
        >
          <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
            <span
              aria-hidden="true"
              style={{
                width: 5,
                height: 5,
                borderRadius: 'var(--radius-full)',
                background: '#FFFFFF',
                animation: 'aitg-dot-bounce 1s ease-in-out infinite',
                animationDelay: '0s',
              }}
            />
            <span
              aria-hidden="true"
              style={{
                width: 5,
                height: 5,
                borderRadius: 'var(--radius-full)',
                background: '#FFFFFF',
                animation: 'aitg-dot-bounce 1s ease-in-out infinite',
                animationDelay: '0.15s',
              }}
            />
            <span
              aria-hidden="true"
              style={{
                width: 5,
                height: 5,
                borderRadius: 'var(--radius-full)',
                background: '#FFFFFF',
                animation: 'aitg-dot-bounce 1s ease-in-out infinite',
                animationDelay: '0.3s',
              }}
            />
          </div>
          {snackbar}
        </div>
      )}
    </main>
  )
}
