import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCheck, faCode, faCopy, faTableList, faVial, faWandMagicSparkles, faXmark } from '@fortawesome/free-solid-svg-icons'
import { faIcon } from '../../faIcon'

const FileCode = faIcon(faCode)
const Vial = faIcon(faVial)
import { ApiError, api, formatTestCaseNumber, type ScenarioRead, type TestAssetStatusRead } from '../../api'
import { Pagination } from '../Pagination'
import { EmptyState, TestCasesIllustration } from '../EmptyState'
import { GenerationLoader } from '../GenerationLoader'
import { SkeletonRows } from '../Skeleton'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'
import { LiveExplorationPanel } from './LiveExplorationPanel'

const ASSETS_PER_PAGE = 10

// Synthesized, not stored — no TestAsset field holds a filename (see
// test_asset.py's own docstring: spec files are named at export/download
// time, not persisted per-asset). Reused for both the code panel's header
// and the card's meta line, so the two always agree.
function specFileName(assetName: string): string {
  return `${assetName}.spec.ts`
}

// Editor-style modal (dark, line-numbered, copy-to-clipboard) matching the
// prototype's codeModalOpen dialog — replaces the old inline <pre> expand.
function CodeModal({ specFile, code, onClose }: { specFile: string; code: string; onClose: () => void }) {
  useEscapeToClose(onClose)
  const [copied, setCopied] = useState(false)
  const lines = code.split('\n')

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // best-effort — clipboard permission denial just skips the confirmation
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 95,
        background: 'rgba(8,9,12,0.6)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 32,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 840,
          maxHeight: '82vh',
          display: 'flex',
          flexDirection: 'column',
          background: '#1E1E1E',
          borderRadius: 16,
          overflow: 'hidden',
          boxShadow: '0 30px 70px rgba(0,0,0,0.5)',
          border: '1px solid #333336',
        }}
      >
        <div style={{ flex: 'none', height: 40, display: 'flex', alignItems: 'center', gap: 10, padding: '0 8px 0 14px', background: '#252526', borderBottom: '1px solid #333336' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 28, padding: '0 12px', borderRadius: '6px 6px 0 0', background: '#1E1E1E', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: '#D4D4D4' }}>
            <FileCode size={11} color="var(--accent-2)" />
            tests/{specFile}
          </div>
          <span style={{ flex: 1 }} />
          <button
            type="button"
            onClick={handleCopy}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px', borderRadius: 6, fontSize: 11, fontWeight: 500, color: '#B4B4B8', cursor: 'pointer', background: 'none', border: 'none' }}
          >
            {copied ? <FontAwesomeIcon icon={faCheck} style={{ fontSize: 10.5 }} /> : <FontAwesomeIcon icon={faCopy} style={{ fontSize: 10.5 }} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 6, color: '#B4B4B8', cursor: 'pointer', background: 'none', border: 'none' }}
          >
            <FontAwesomeIcon icon={faXmark} style={{ fontSize: 12 }} />
          </button>
        </div>
        <div style={{ flex: 1, overflow: 'auto', display: 'flex' }}>
          <div style={{ flex: 'none', padding: '16px 12px 16px 16px', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: '20px', color: '#5A5A60', textAlign: 'right', userSelect: 'none', background: '#1E1E1E' }}>
            {lines.map((_, i) => (
              <div key={i}>{i + 1}</div>
            ))}
          </div>
          <pre style={{ flex: 1, margin: 0, padding: '16px 20px 16px 8px', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: '20px', color: '#D4D4D4', overflowX: 'auto', whiteSpace: 'pre' }}>{code}</pre>
        </div>
      </div>
    </div>
  )
}

export function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--fg-5)"
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

const REGENERATE_POLL_INTERVAL_MS = 3000
const AUTOFILL_POLL_INTERVAL_MS = 500

const SOURCE_LABEL: Record<TestAssetStatusRead['source'], string> = {
  discovery: 'From discovery',
  nl: 'Authored by prompt',
}

// Edit Test Data (Test Suite page) — inline, expanded-row form, reusing the
// same field-list markup/behavior ReviewScenarios.tsx already established
// for this exact data (Scenario.test_data). Unlike that screen's
// per-field-onBlur save, edits here are held in local `draft` state and
// only persisted on an explicit Save — and only once every changed field
// has saved successfully does this trigger a targeted AI regeneration of
// the Scenario's current TestAsset, so "Save" always means "and update the
// compiled test to match."
function TestDataEditor({
  scenario,
  onScenarioUpdated,
  onDone,
}: {
  scenario: ScenarioRead
  onScenarioUpdated: (updated: ScenarioRead) => void
  onDone: () => void
}) {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(scenario.test_data.map((field) => [field.name, field.value ?? ''])),
  )
  const [saving, setSaving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function pollUntilTerminal(scenarioId: string): Promise<void> {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      await new Promise((resolve) => setTimeout(resolve, REGENERATE_POLL_INTERVAL_MS))
      const status = await api.getRegenerateTestAssetStatus(scenarioId)
      if (status.status === 'complete') {
        onDone()
        return
      }
      if (status.status === 'failed') {
        setError(
          status.error_message ??
            "Could not update this test's code — the previous version is still in use.",
        )
        return
      }
    }
  }

  async function handleSave() {
    setError(null)
    setSaving(true)
    let updated = scenario
    try {
      for (const field of scenario.test_data) {
        const value = draft[field.name] ?? ''
        if (value !== (field.value ?? '')) {
          updated = await api.updateScenarioTestData(scenario.id, field.name, value)
        }
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save test data')
      setSaving(false)
      return
    }
    onScenarioUpdated(updated)
    setSaving(false)

    setRegenerating(true)
    try {
      await api.regenerateTestAsset(scenario.id)
      await pollUntilTerminal(scenario.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to regenerate this test')
    } finally {
      setRegenerating(false)
    }
  }

  const busy = saving || regenerating

  return (
    <div
      style={{
        background: 'var(--panel-2)',
        border: '1px solid var(--border-2)',
        borderRadius: 10,
        padding: 16,
        marginTop: 10,
        display: 'flex',
        flexDirection: 'column',
        gap: 13,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
        <FontAwesomeIcon icon={faTableList} style={{ fontSize: 12, color: "var(--accent-2)" }} />
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', flex: 1 }}>Test data</span>
        <span
          style={{
            fontSize: 10.5,
            fontWeight: 600,
            padding: '2px 8px',
            borderRadius: 6,
            background: scenario.test_data_complete ? 'rgba(30,150,138,0.14)' : 'var(--chip)',
            color: scenario.test_data_complete ? 'var(--accent-2)' : 'var(--fg-3)',
            border: `1px solid ${scenario.test_data_complete ? 'rgba(30,150,138,0.28)' : 'var(--border-2)'}`,
          }}
        >
          {scenario.test_data_complete ? 'Complete' : 'Incomplete'}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 13 }}>
        {scenario.test_data.map((field) => (
          <label key={field.name} style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)' }}>
              {field.name}
              {field.mandatory && (
                <span style={{ color: 'var(--danger)' }} aria-label="required">
                  {' '}
                  *
                </span>
              )}
            </span>
            <input
              value={draft[field.name] ?? ''}
              placeholder={`Enter ${field.name}`}
              disabled={busy}
              onChange={(e) => setDraft((d) => ({ ...d, [field.name]: e.target.value }))}
              style={{
                height: 34,
                padding: '0 10px',
                border: '1px solid var(--border-2)',
                borderRadius: 7,
                fontSize: 12.5,
                color: 'var(--fg-1)',
                background: 'var(--panel)',
                outline: 'none',
                width: '100%',
                boxSizing: 'border-box',
                fontFamily: 'inherit',
              }}
            />
          </label>
        ))}
      </div>
      {error && <p style={{ color: 'var(--danger-strong)', fontSize: 12, margin: 0 }}>{error}</p>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={handleSave}
          disabled={busy}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            height: 32,
            padding: '0 14px',
            borderRadius: 8,
            border: 'none',
            fontSize: 12.5,
            fontWeight: 600,
            color: '#fff',
            background: busy ? 'var(--fg-4)' : 'var(--accent)',
            boxShadow: busy ? 'none' : '0 4px 14px rgba(30,150,138,0.3)',
            cursor: busy ? 'default' : 'pointer',
          }}
        >
          {regenerating ? 'Regenerating…' : saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

function AssetCard({
  asset,
  scenario,
  onScenarioUpdated,
  onRegenerated,
}: {
  asset: TestAssetStatusRead
  scenario: ScenarioRead | null
  onScenarioUpdated: (updated: ScenarioRead) => void
  onRegenerated: () => void
}) {
  const [codeOpen, setCodeOpen] = useState(false)
  const [code, setCode] = useState<string | null>(null)
  const [codeError, setCodeError] = useState<string | null>(null)
  const [loadingCode, setLoadingCode] = useState(false)
  const [showTestData, setShowTestData] = useState(false)

  async function handleViewCode() {
    setCodeOpen((open) => !open)
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

  return (
    <div
      style={{
        background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
        backdropFilter: 'blur(16px) saturate(1.25)',
        border: '1px solid var(--border-1)',
        borderRadius: 14,
        overflow: 'hidden',
        boxShadow: 'var(--panel-shadow)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '17px 20px', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: 'var(--fg-5)' }}>
              {formatTestCaseNumber(asset.test_case_number)}
            </span>
            <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.01em' }}>{asset.name}</span>
            {/* NL Test Case badge — only a test case genuinely created via
                live browser exploration carries source:'nl'. */}
            {asset.source === 'nl' && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10.5, fontWeight: 600, padding: '2px 8px', borderRadius: 6, background: 'rgba(30,150,138,0.14)', color: 'var(--accent-2)', border: '1px solid rgba(30,150,138,0.28)' }}>
                Authored by prompt
              </span>
            )}
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 6, maxWidth: 760, lineHeight: '19px' }}>
            {scenario?.expected_result || 'No expected result recorded'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11.5, color: 'var(--fg-4)' }}>{asset.journey_name}</span>
            <span style={{ width: 3, height: 3, borderRadius: 1000, background: 'var(--fg-6)' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-4)' }}>{specFileName(asset.name)}</span>
            <span style={{ width: 3, height: 3, borderRadius: 1000, background: 'var(--fg-6)' }} />
            <span style={{ fontSize: 11.5, color: asset.source === 'nl' ? 'var(--accent-2)' : 'var(--fg-4)' }}>
              {SOURCE_LABEL[asset.source]}
            </span>
          </div>
          {asset.steps.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 11 }}>
              {asset.steps.map((step, i) => (
                <span key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, padding: '3px 8px', borderRadius: 5, background: 'var(--panel-2)', border: '1px solid var(--border-2)', color: 'var(--fg-4)' }}>
                  {step}
                </span>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 'none' }}>
          <button
            type="button"
            onClick={handleViewCode}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, padding: '0 12px', borderRadius: 8, border: '1px solid var(--border-2)', background: codeOpen ? 'var(--hover)' : 'var(--panel-2)', fontSize: 12, fontWeight: 500, color: 'var(--fg-2)', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            <FileCode size={11} />
            {loadingCode ? 'Loading…' : 'View code'}
          </button>
          {scenario && (
            <button
              type="button"
              onClick={() => setShowTestData((o) => !o)}
              disabled={scenario.test_data.length === 0}
              title={scenario.test_data.length === 0 ? 'This test case has no test data fields' : undefined}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 7,
                height: 30,
                padding: '0 12px',
                borderRadius: 8,
                border: '1px solid var(--border-2)',
                background: showTestData ? 'var(--hover)' : 'var(--panel-2)',
                fontSize: 12,
                fontWeight: 500,
                color: 'var(--fg-2)',
                cursor: scenario.test_data.length === 0 ? 'not-allowed' : 'pointer',
                opacity: scenario.test_data.length === 0 ? 0.5 : 1,
                whiteSpace: 'nowrap',
              }}
            >
              <FontAwesomeIcon icon={faTableList} style={{ fontSize: 11 }} />
              Test data
            </button>
          )}
        </div>
      </div>

      {codeError && (
        <p style={{ color: 'var(--bad)', fontSize: 12, margin: '0 20px 16px' }}>{codeError}</p>
      )}

      {codeOpen && code != null && (
        <CodeModal specFile={specFileName(asset.name)} code={code} onClose={() => setCodeOpen(false)} />
      )}

      {showTestData && scenario && (
        <div style={{ padding: '0 20px 20px' }}>
          <TestDataEditor
            scenario={scenario}
            onScenarioUpdated={onScenarioUpdated}
            onDone={() => {
              onRegenerated()
              setShowTestData(false)
            }}
          />
        </div>
      )}
    </div>
  )
}

export function TestSuiteTab({
  applicationId,
}: {
  applicationId: string
}) {
  const [assets, setAssets] = useState<TestAssetStatusRead[]>([])
  const [assetsLoaded, setAssetsLoaded] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  // Edit Test Data — fetched once per page load/refresh here (not once per
  // row) since every row needing this data would otherwise each fetch the
  // full per-Application scenario list independently, same reuse of
  // api.listScenarios ReviewScenarios.tsx already establishes.
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([])
  // Auto-generate data (bulk) — loops the existing per-scenario auto-fill
  // endpoint across every scenario still missing test data, one at a time
  // (no bulk endpoint on the backend; this is client-side orchestration of
  // the same action ReviewScenarios.tsx/TestDataEditor already trigger
  // individually).
  const [bulkAutofill, setBulkAutofill] = useState<{ done: number; total: number } | null>(null)
  const [bulkAutofillError, setBulkAutofillError] = useState<string | null>(null)
  // Distinguishes "generation hasn't started" from "generation is running
  // but hasn't produced a test case yet" — same GenerationLoader-vs-EmptyState
  // split ReviewScenarios.tsx already makes for scenarios, so this screen's
  // empty state doesn't lie while a suite is actively being written.
  const [suiteGenerating, setSuiteGenerating] = useState(false)
  // "Author a test case" (natural language) — lives on this tab per the
  // prototype's isData screen (toggleAuthor), not on Scenarios.
  const [authoringOpen, setAuthoringOpen] = useState(false)
  const totalPages = Math.max(1, Math.ceil(total / ASSETS_PER_PAGE))
  const scenariosById = Object.fromEntries(scenarios.map((s) => [s.id, s]))

  function refreshAssets() {
    return api.getTestSuiteStatus(applicationId, page + 1, ASSETS_PER_PAGE, search).then((body) => {
      setAssets(body.items)
      setTotal(body.total)
    })
  }

  async function handleAutoGenerateAllData() {
    if (bulkAutofill) return
    const pending = scenarios.filter((s) => !s.test_data_complete)
    if (pending.length === 0) return
    setBulkAutofillError(null)
    setBulkAutofill({ done: 0, total: pending.length })
    let failures = 0
    for (const [i, scenario] of pending.entries()) {
      try {
        await api.autofillScenarioTestData(scenario.id)
        let result = await api.getAutofillScenarioTestDataStatus(scenario.id)
        while (result.status === 'running') {
          await new Promise((resolve) => setTimeout(resolve, AUTOFILL_POLL_INTERVAL_MS))
          result = await api.getAutofillScenarioTestDataStatus(scenario.id)
        }
        if (result.status === 'complete' && result.scenario) {
          setScenarios((rows) => rows.map((s) => (s.id === scenario.id ? result.scenario! : s)))
        } else {
          failures += 1
        }
      } catch {
        failures += 1
      }
      setBulkAutofill({ done: i + 1, total: pending.length })
    }
    setBulkAutofill(null)
    if (failures > 0) {
      setBulkAutofillError(
        failures === pending.length
          ? 'Could not auto-generate test data.'
          : `Auto-generated data for ${pending.length - failures} of ${pending.length} test cases — ${failures} failed.`,
      )
    }
  }

  useEffect(() => {
    let cancelled = false
    api.getTestSuiteStatus(applicationId, page + 1, ASSETS_PER_PAGE, search).then(
      (body) => {
        if (!cancelled) {
          setAssets(body.items)
          setTotal(body.total)
          setAssetsLoaded(true)
        }
      },
      () => {
        if (!cancelled) setAssetsLoaded(true)
      },
    )
    return () => {
      cancelled = true
    }
  }, [applicationId, page, search])

  useEffect(() => {
    let cancelled = false
    api.listScenarios(applicationId).then((body) => {
      if (!cancelled) setScenarios(body)
    })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  // Only while the page is genuinely empty (no search/pagination in play) —
  // polls for a suite still writing its first test case, and picks up the
  // asset list itself the moment one lands, rather than waiting on the
  // page/search-keyed effect above to happen to re-run.
  useEffect(() => {
    if (!assetsLoaded || assets.length > 0 || search || page !== 0) return
    let cancelled = false
    async function poll() {
      try {
        const [suites, statusPage] = await Promise.all([
          api.listTestSuites(applicationId),
          api.getTestSuiteStatus(applicationId, 1, ASSETS_PER_PAGE, ''),
        ])
        if (cancelled) return
        setSuiteGenerating(suites.some((s) => s.status === 'generating'))
        if (statusPage.items.length > 0) {
          setAssets(statusPage.items)
          setTotal(statusPage.total)
        }
      } catch {
        // best-effort poll — a transient failure just leaves the empty state as-is
      }
    }
    poll()
    const interval = setInterval(poll, REGENERATE_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId, assetsLoaded, assets.length, search, page])

  const pendingAutofillCount = scenarios.filter((s) => !s.test_data_complete).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {pendingAutofillCount > 0 && (
          <button
            type="button"
            onClick={handleAutoGenerateAllData}
            disabled={!!bulkAutofill}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 14px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', fontSize: 12.5, fontWeight: 500, color: 'var(--fg-2)', cursor: bulkAutofill ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
          >
            <FontAwesomeIcon icon={faWandMagicSparkles} style={{ fontSize: 12 }} />
            {bulkAutofill ? 'Generating…' : 'Auto-generate data'}
          </button>
        )}
        {bulkAutofill && (
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 90, height: 4, borderRadius: 1000, background: 'var(--chip)', overflow: 'hidden' }}>
              <div style={{ width: `${(bulkAutofill.done / bulkAutofill.total) * 100}%`, height: '100%', background: 'var(--accent-2)' }} />
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--fg-3)', whiteSpace: 'nowrap' }}>
              {bulkAutofill.done} of {bulkAutofill.total}
            </span>
          </div>
        )}
        <span style={{ flex: 1 }} />
        <input
          id="test-suite-search"
          type="text"
          aria-label="Search by Test Case number, name, or Journey"
          placeholder="Search test cases"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(0)
          }}
          style={{ width: 240, maxWidth: '100%', boxSizing: 'border-box', height: 34, padding: '0 12px', border: '1px solid var(--border-2)', borderRadius: 8, fontSize: 13, fontFamily: 'inherit', color: 'var(--fg-1)', background: 'var(--panel)' }}
        />
        <button
          type="button"
          onClick={() => setAuthoringOpen((open) => !open)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            height: 34,
            padding: '0 14px',
            whiteSpace: 'nowrap',
            background: authoringOpen ? 'rgba(30,150,138,0.14)' : 'var(--panel)',
            color: 'var(--accent-2)',
            border: `1px solid rgba(30,150,138,${authoringOpen ? 0.45 : 0.3})`,
            borderRadius: 8,
            fontSize: 12.5,
            fontWeight: 600,
            fontFamily: 'inherit',
            cursor: 'pointer',
          }}
        >
          <FontAwesomeIcon icon={authoringOpen ? faXmark : faWandMagicSparkles} style={{ fontSize: 11 }} />
          Author a test case
        </button>
      </div>
      {authoringOpen && (
        <LiveExplorationPanel applicationId={applicationId} onClose={() => setAuthoringOpen(false)} />
      )}
      {bulkAutofillError && (
        <p role="alert" style={{ color: 'var(--danger-strong)', fontSize: 13, margin: 0 }}>
          {bulkAutofillError}
        </p>
      )}
      {!assetsLoaded ? (
        <SkeletonRows count={4} height={80} gap={12} />
      ) : assets.length === 0 ? (
        search ? (
          <p style={{ fontSize: 13, color: 'var(--fg-4)' }}>No test cases match this search.</p>
        ) : suiteGenerating ? (
          <GenerationLoader
            icon={Vial}
            title="Writing test cases…"
            body="Vantage is turning approved scenarios into test cases with generated fixtures. Nothing to review until the suite is written."
          />
        ) : (
          <EmptyState
            illustration={<TestCasesIllustration />}
            title="No test cases generated yet"
            subtitle="Test cases appear here once discovery finds journeys and the suite is generated."
          />
        )
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {assets.map((asset) => (
              <AssetCard
                key={asset.id}
                asset={asset}
                scenario={asset.scenario_id ? (scenariosById[asset.scenario_id] ?? null) : null}
                onScenarioUpdated={(updated) =>
                  setScenarios((rows) => rows.map((s) => (s.id === updated.id ? updated : s)))
                }
                onRegenerated={refreshAssets}
              />
            ))}
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            totalItems={total}
            pageSize={ASSETS_PER_PAGE}
            onPrev={() => setPage((p) => p - 1)}
            onNext={() => setPage((p) => p + 1)}
            onPage={setPage}
          />
        </>
      )}
    </div>
  )
}
