import { useEffect, useRef, useState } from 'react'
import { api, type ScenarioRead } from '../api'
import { Stepper } from './Stepper'

const POLL_INTERVAL_MS = 1500

const TYPE_BADGE: Record<string, { label: string; background: string; color: string }> = {
  happy: { label: 'Happy Path', background: 'var(--good-wash)', color: 'var(--good)' },
  negative: { label: 'Negative Path', background: 'var(--danger-wash)', color: 'var(--danger)' },
  edge: { label: 'Edge Case', background: 'var(--warn-wash)', color: 'var(--warn)' },
}

function ScenarioRenameInput({
  initialName,
  onSave,
  onCancel,
}: {
  initialName: string
  onSave: (name: string) => void
  onCancel: () => void
}) {
  const [value, setValue] = useState(initialName)
  const cancelledRef = useRef(false)

  return (
    <input
      autoFocus
      value={value}
      aria-label="Scenario name"
      onChange={(e) => setValue(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur()
        if (e.key === 'Escape') {
          cancelledRef.current = true
          onCancel()
        }
      }}
      onBlur={() => {
        if (cancelledRef.current) return
        const trimmed = value.trim()
        if (trimmed) onSave(trimmed)
        else onCancel()
      }}
      style={{
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius)',
        padding: '4px 8px',
        fontSize: 14,
        flex: 1,
        marginRight: 'var(--space-3)',
      }}
    />
  )
}

function ScenarioRowMenu({ onRename, onDelete }: { onRename: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false)

  return (
    <div style={{ position: 'relative' }} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Scenario actions"
        onClick={() => setOpen((o) => !o)}
        style={{
          width: 26,
          height: 26,
          borderRadius: 'var(--radius)',
          background: 'transparent',
          border: 'none',
          color: 'var(--ink-muted)',
          cursor: 'pointer',
          fontSize: 16,
          lineHeight: 1,
        }}
      >
        ⋯
      </button>
      {open && (
        <div
          role="menu"
          className="card-panel"
          style={{
            position: 'absolute',
            right: 0,
            top: 30,
            minWidth: 140,
            boxShadow: '0 12px 28px rgba(15,23,42,0.14)',
            overflow: 'hidden',
            zIndex: 10,
          }}
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onRename()
            }}
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              padding: '9px 12px',
              background: 'none',
              border: 'none',
              fontSize: 13,
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            Rename
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onDelete()
            }}
            className="menu-item-danger"
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              padding: '9px 12px',
              background: 'none',
              border: 'none',
              fontSize: 13,
              color: 'var(--danger)',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            Remove
          </button>
        </div>
      )}
    </div>
  )
}

export function ReviewScenarios({
  applicationId,
  onContinueToGenerate,
}: {
  applicationId: string
  onContinueToGenerate: () => void
}) {
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const rows = await api.listScenarios(applicationId)
        if (!cancelled) setScenarios(rows)
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
    }

    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId])

  async function handleRename(id: string, name: string) {
    setRenamingId(null)
    const updated = await api.renameScenario(id, name)
    setScenarios((rows) => rows.map((s) => (s.id === id ? updated : s)))
  }

  async function handleDelete(id: string) {
    if (!window.confirm('Remove this Scenario?')) return
    await api.deleteScenario(id)
    setScenarios((rows) => rows.filter((s) => s.id !== id))
    setSelectedId((current) => (current === id ? null : current))
  }

  async function handleTestDataChange(scenarioId: string, name: string, value: string) {
    const updated = await api.updateScenarioTestData(scenarioId, name, value)
    setScenarios((rows) => rows.map((s) => (s.id === scenarioId ? updated : s)))
  }

  const selectedScenario = scenarios.find((s) => s.id === selectedId) ?? null
  // `[UPDATED]` No longer gated on test_data completeness — any blank field
  // (missed by the reviewer, or never filled in at all) gets a sensible
  // default at generation time (PlaywrightGenerationActivity, Story 4.2).
  // Enabled as soon as there's at least one Scenario to generate from.
  const canContinue = scenarios.length > 0

  return (
    <>
      <Stepper current="review" />
      <main
        style={{
          maxWidth: 'var(--content-max)',
          margin: '0 auto',
          padding: `var(--content-top) var(--content-x)`,
        }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 650, margin: '0 0 8px' }}>Review Scenarios</h1>

        <div
          className="card-panel"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: 'var(--space-4) var(--space-5)',
            marginBottom: 'var(--space-4)',
            gap: 'var(--space-4)',
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600 }}>
            {scenarios.length} Scenario{scenarios.length === 1 ? '' : 's'}
          </div>
          <button
            type="button"
            onClick={onContinueToGenerate}
            disabled={!canContinue}
            style={{
              padding: '10px 20px',
              whiteSpace: 'nowrap',
              background: canContinue ? 'var(--signal)' : 'var(--border)',
              color: canContinue ? 'var(--signal-ink)' : 'var(--ink-faint)',
              border: 'none',
              borderRadius: 'var(--radius)',
              fontSize: 14,
              fontWeight: 600,
              fontFamily: 'inherit',
              cursor: canContinue ? 'pointer' : 'not-allowed',
            }}
          >
            Continue to Generate Test Suite →
          </button>
        </div>

        {scenarios.length === 0 ? (
          <p className="caption">
            No Scenarios yet — generation runs in the background after clicking "Continue to
            Scenarios."
          </p>
        ) : (
          <div style={{ display: 'flex', gap: 'var(--space-5)', alignItems: 'flex-start' }}>
            <ul
              style={{
                listStyle: 'none',
                margin: 0,
                padding: 0,
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-2)',
              }}
            >
              {scenarios.map((scenario) => {
                const badge = TYPE_BADGE[scenario.type] ?? TYPE_BADGE.happy
                return (
                  <li
                    key={scenario.id}
                    className="card-panel card-clickable"
                    onClick={() => setSelectedId(scenario.id)}
                    style={{
                      padding: 'var(--space-3) var(--space-4)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      borderColor: selectedId === scenario.id ? 'var(--signal)' : undefined,
                    }}
                  >
                    {renamingId === scenario.id ? (
                      <ScenarioRenameInput
                        initialName={scenario.name}
                        onSave={(name) => handleRename(scenario.id, name)}
                        onCancel={() => setRenamingId(null)}
                      />
                    ) : (
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{scenario.name}</div>
                        <div className="caption" style={{ fontSize: 12, marginBottom: 4 }}>
                          from {scenario.journey_name}
                        </div>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '2px 8px',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: 11,
                            fontWeight: 650,
                            background: badge.background,
                            color: badge.color,
                          }}
                        >
                          {badge.label}
                        </span>
                        {!scenario.test_data_complete && (
                          <span className="caption" style={{ fontSize: 11, marginLeft: 8 }}>
                            Test data incomplete
                          </span>
                        )}
                      </div>
                    )}
                    <ScenarioRowMenu
                      onRename={() => setRenamingId(scenario.id)}
                      onDelete={() => handleDelete(scenario.id)}
                    />
                  </li>
                )
              })}
            </ul>

            <div
              className="card-panel"
              style={{
                width: 380,
                flexShrink: 0,
                padding: 'var(--space-4)',
                position: 'sticky',
                top: 'var(--space-4)',
              }}
            >
              {selectedScenario ? (
                <>
                  <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 'var(--space-1)' }}>
                    {selectedScenario.name}
                  </div>
                  <div className="caption" style={{ fontSize: 12, marginBottom: 'var(--space-4)' }}>
                    from {selectedScenario.journey_name}
                  </div>

                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 'var(--space-2)' }}>
                    Test steps
                  </div>
                  <ol style={{ margin: '0 0 var(--space-4)', paddingLeft: 20 }}>
                    {selectedScenario.steps.map((step, index) => (
                      <li key={index} style={{ fontSize: 13, marginBottom: 6 }}>
                        {step}
                      </li>
                    ))}
                  </ol>

                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 'var(--space-2)' }}>
                    Test data
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 'var(--space-2)',
                      marginBottom: 'var(--space-4)',
                    }}
                  >
                    {selectedScenario.test_data.map((field) => (
                      <label key={field.name} className="field">
                        <span style={{ fontSize: 12 }}>
                          {field.name}
                          {field.mandatory && (
                            <span style={{ color: 'var(--danger)' }} aria-label="required">
                              {' '}
                              *
                            </span>
                          )}
                        </span>
                        <input
                          defaultValue={field.value ?? ''}
                          onBlur={(e) =>
                            handleTestDataChange(selectedScenario.id, field.name, e.target.value)
                          }
                        />
                      </label>
                    ))}
                  </div>

                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 'var(--space-2)' }}>
                    Expected result
                  </div>
                  <div
                    style={{
                      background: 'var(--surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      padding: 'var(--space-3)',
                      fontSize: 13,
                    }}
                  >
                    {selectedScenario.expected_result}
                  </div>
                </>
              ) : (
                <p className="caption" style={{ margin: 0 }}>
                  Select a Scenario to see its Test steps, Test data, and Expected result.
                </p>
              )}
            </div>
          </div>
        )}
      </main>
    </>
  )
}
