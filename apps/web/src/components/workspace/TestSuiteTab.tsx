import { useEffect, useState } from 'react'
import { ApiError, api, type TestAssetStatusRead, type TestResultRead } from '../../api'
import { CodeModal } from '../TestSuiteResults'
import { StatusPill } from '../StatusPill'
import { ArtifactsModal } from './RunsTab'
import { Pagination } from '../Pagination'

const ASSETS_PER_PAGE = 5

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

// First column (Test Case name) gets 45% of the row; the rest — Last Run,
// Duration, Status — split the remaining width evenly. Same template on the
// header and every row keeps the columns lined up.
const ASSET_GRID_TEMPLATE = '45% 1fr 1fr 1fr'

type AssetSortKey = 'name' | 'lastRun' | 'duration' | 'status'

function ColumnHeaderLabel({
  children,
  align,
  sortKey,
  activeKey,
  dir,
  onSort,
}: {
  children: string
  align?: 'right'
  sortKey?: AssetSortKey
  activeKey?: AssetSortKey | null
  dir?: 'asc' | 'desc'
  onSort?: (key: AssetSortKey) => void
}) {
  const isActive = sortKey != null && sortKey === activeKey
  return (
    <span
      onClick={sortKey && onSort ? () => onSort(sortKey) : undefined}
      style={{
        fontSize: 11,
        fontWeight: 700,
        color: 'var(--ink-faint)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        whiteSpace: 'nowrap',
        textAlign: align,
        cursor: sortKey ? 'pointer' : undefined,
        userSelect: sortKey ? 'none' : undefined,
      }}
    >
      {children}
      {isActive ? (dir === 'asc' ? ' ▲' : ' ▼') : ''}
    </span>
  )
}

function formatLastRun(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function assetSortValue(asset: TestAssetStatusRead, key: AssetSortKey): string | number {
  switch (key) {
    case 'name':
      return asset.name.toLowerCase()
    case 'lastRun':
      return asset.last_run_at ?? ''
    case 'duration':
      return asset.duration_ms ?? -1
    case 'status':
      return asset.status
  }
}

// Sorts only the currently-loaded page — the list API has no `sort` param,
// and re-sorting across pages would mean fetching every page up front.
function sortAssets(assets: TestAssetStatusRead[], key: AssetSortKey, dir: 'asc' | 'desc'): TestAssetStatusRead[] {
  const sorted = [...assets].sort((a, b) => {
    const av = assetSortValue(a, key)
    const bv = assetSortValue(b, key)
    if (av < bv) return -1
    if (av > bv) return 1
    return 0
  })
  return dir === 'asc' ? sorted : sorted.reverse()
}

function AssetListHeader({
  sortKey,
  sortDir,
  onSort,
}: {
  sortKey: AssetSortKey | null
  sortDir: 'asc' | 'desc'
  onSort: (key: AssetSortKey) => void
}) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: ASSET_GRID_TEMPLATE,
        alignItems: 'center',
        gap: 20,
        padding: '8px 16px',
        background: 'var(--canvas-wash-alt)',
        borderBottom: '1px solid var(--border-hairline)',
      }}
    >
      {/* 24px = chevron (14) + its gap (10) in each row below, so the label lines up over the row's text, not its icon. */}
      <div style={{ paddingLeft: 24, minWidth: 0 }}>
        <ColumnHeaderLabel sortKey="name" activeKey={sortKey} dir={sortDir} onSort={onSort}>
          Test Case
        </ColumnHeaderLabel>
      </div>
      <ColumnHeaderLabel sortKey="lastRun" activeKey={sortKey} dir={sortDir} onSort={onSort}>
        Last Run
      </ColumnHeaderLabel>
      <ColumnHeaderLabel sortKey="duration" activeKey={sortKey} dir={sortDir} onSort={onSort}>
        Duration
      </ColumnHeaderLabel>
      <ColumnHeaderLabel sortKey="status" activeKey={sortKey} dir={sortDir} onSort={onSort}>
        Status
      </ColumnHeaderLabel>
    </div>
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
          display: 'grid',
          gridTemplateColumns: ASSET_GRID_TEMPLATE,
          alignItems: 'center',
          gap: 20,
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
        <span className="caption" style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>
          {formatLastRun(asset.last_run_at)}
        </span>
        <span className="caption" style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>
          {asset.duration_ms != null ? `${(asset.duration_ms / 1000).toFixed(1)}s` : '—'}
        </span>
        <span>
          <StatusPill status={asset.status} />
        </span>
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

export function TestSuiteTab({ applicationId }: { applicationId: string }) {
  const [assets, setAssets] = useState<TestAssetStatusRead[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [sortKey, setSortKey] = useState<AssetSortKey | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const totalPages = Math.max(1, Math.ceil(total / ASSETS_PER_PAGE))
  const sortedAssets = sortKey ? sortAssets(assets, sortKey, sortDir) : assets
  function handleSort(key: AssetSortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

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

  return (
    <div>
      {assets.length === 0 ? (
        <p className="caption" style={{ fontSize: 13 }}>
          No tests generated yet.
        </p>
      ) : (
        <div className="card-panel" style={{ overflow: 'hidden' }}>
          <AssetListHeader sortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
          {sortedAssets.map((asset) => (
            <AssetRow key={asset.id} asset={asset} />
          ))}
          <Pagination
            page={page}
            totalPages={totalPages}
            totalItems={total}
            pageSize={ASSETS_PER_PAGE}
            onPrev={() => setPage((p) => p - 1)}
            onNext={() => setPage((p) => p + 1)}
            onPage={setPage}
          />
        </div>
      )}
    </div>
  )
}
