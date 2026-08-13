import { useEffect, useState } from 'react'
import { ApiError, api, type TestAssetStatusRead, type TestResultRead } from '../../api'
import { CodeModal } from '../TestSuiteResults'
import { StatusPill } from '../StatusPill'
import { ArtifactsModal } from './RunsTab'

const ASSETS_PER_PAGE = 10

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--ink-faint)"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s ease' }}
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

function assetToTestResult(asset: TestAssetStatusRead): TestResultRead | null {
  if (!asset.latest_test_result_id) return null
  return {
    id: asset.latest_test_result_id,
    scenario_name: asset.name,
    status: 'failed',
    duration_ms: asset.duration_ms,
    error_message: asset.error_message,
    stack_trace: null,
    blocked_reason: null,
  }
}

function AssetRow({ asset }: { asset: TestAssetStatusRead }) {
  const [expanded, setExpanded] = useState(false)
  const [code, setCode] = useState<string | null>(null)
  const [codeError, setCodeError] = useState<string | null>(null)
  const [loadingCode, setLoadingCode] = useState(false)
  const [showArtifacts, setShowArtifacts] = useState(false)

  async function handleViewCode() {
    if (code == null && !loadingCode) {
      setLoadingCode(true)
      try {
        const body = await api.getTestAssetCode(asset.id)
        setCode(body.code)
      } catch (err) {
        setCodeError(err instanceof ApiError ? err.message : 'Failed to load code')
      } finally {
        setLoadingCode(false)
      }
    }
  }

  const testResult = assetToTestResult(asset)

  return (
    <div style={{ borderBottom: '1px solid var(--border-hairline)' }}>
      <button
        type="button"
        onClick={() => setExpanded((o) => !o)}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          width: '100%',
          padding: '12px 16px',
          background: 'none',
          border: 'none',
          textAlign: 'left',
          fontFamily: 'inherit',
          cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <ChevronIcon open={expanded} />
          <span
            style={{
              fontSize: 13,
              color: 'var(--ink)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {asset.name}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
          {asset.duration_ms != null && (
            <span className="caption" style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>
              {(asset.duration_ms / 1000).toFixed(1)}s
            </span>
          )}
          <StatusPill status={asset.status} />
        </div>
      </button>

      {expanded && (
        <div style={{ padding: '0 16px 14px 40px' }}>
          {asset.steps.length > 0 && (
            <ol style={{ margin: '0 0 10px', padding: '0 0 0 18px', fontSize: 12.5, color: 'var(--ink-secondary)', lineHeight: 1.6 }}>
              {asset.steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          )}
          {asset.status === 'failed' && asset.error_message && (
            <pre
              style={{
                margin: '0 0 10px',
                padding: 10,
                background: 'var(--canvas-wash)',
                border: '1px solid var(--border-hairline)',
                borderRadius: 'var(--radius)',
                fontSize: 11.5,
                lineHeight: 1.5,
                color: 'var(--danger-strong)',
                fontFamily: "'SFMono-Regular',Consolas,monospace",
                whiteSpace: 'pre-wrap',
                overflow: 'auto',
                maxHeight: 160,
              }}
            >
              {asset.error_message}
            </pre>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="button-secondary" onClick={handleViewCode}>
              {loadingCode ? 'Loading…' : 'View Code'}
            </button>
            {asset.status === 'failed' && testResult && (
              <button type="button" className="button-secondary" onClick={() => setShowArtifacts(true)}>
                Artifacts
              </button>
            )}
          </div>
          {codeError && (
            <p style={{ color: 'var(--danger-strong)', fontSize: 12, margin: '8px 0 0' }}>{codeError}</p>
          )}
        </div>
      )}

      {code != null && <CodeModal testCase={{ name: asset.name, code }} onClose={() => setCode(null)} />}
      {showArtifacts && testResult && (
        <ArtifactsModal testResult={testResult} onClose={() => setShowArtifacts(false)} />
      )}
    </div>
  )
}

export function TestSuiteTab({
  applicationId,
  onRunStarted,
}: {
  applicationId: string
  onRunStarted: () => void
}) {
  const [assets, setAssets] = useState<TestAssetStatusRead[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const totalPages = Math.max(1, Math.ceil(total / ASSETS_PER_PAGE))

  useEffect(() => {
    let cancelled = false
    api.getTestSuiteStatus(applicationId, page + 1, ASSETS_PER_PAGE).then((body) => {
      if (!cancelled) {
        setAssets(body.items)
        setTotal(body.total)
      }
    })
    return () => {
      cancelled = true
    }
  }, [applicationId, page])

  async function handleRunSuite() {
    setRunning(true)
    setRunError(null)
    try {
      await api.triggerTestRun(applicationId)
      onRunStarted()
    } catch (err) {
      setRunError(err instanceof ApiError ? err.message : 'Failed to start the test run')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
        <button type="button" className="button-primary" disabled={running} onClick={handleRunSuite}>
          {running ? 'Starting…' : 'Run Suite'}
        </button>
      </div>
      {runError && (
        <p role="alert" style={{ color: 'var(--danger-strong)', fontSize: 13 }}>
          {runError}
        </p>
      )}

      {assets.length === 0 ? (
        <p className="caption" style={{ fontSize: 13 }}>
          No tests generated yet.
        </p>
      ) : (
        <div className="card-panel" style={{ overflow: 'hidden' }}>
          {assets.map((asset) => (
            <AssetRow key={asset.id} asset={asset} />
          ))}
          {totalPages > 1 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 'var(--space-3)',
                padding: 'var(--space-4) var(--space-5)',
              }}
            >
              <button
                type="button"
                className="button-secondary"
                disabled={page <= 0}
                onClick={() => setPage((p) => p - 1)}
              >
                Prev
              </button>
              <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                Page {page + 1} of {totalPages}
              </span>
              <button
                type="button"
                className="button-secondary"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
